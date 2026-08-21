import logging
import math
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

from app.crowd_analysis import DenseCrowdAnalysisDecision
from app.database.video_job_repository import (
    CreatedVideoJob,
    complete_video_analysis_job,
    create_video_analysis_job,
    fail_video_analysis_job,
    get_video_analysis_job,
    mark_video_job_processing,
    update_video_job_progress,
)
from app.model_profile import RuntimeModelProfile
from app.services.frame_sampling_service import (
    calculate_sampled_frame_count,
    sample_video_frames,
)
from app.services.grid_counting_service import count_detections_by_grid
from app.services.output_service import save_image_output
from app.services.video_detection_service import process_sampled_video_frames
from app.services.video_service import VideoReader
from app.services.video_upload_service import (
    StoredVideoUpload,
    VideoUploadPolicy,
    store_validated_video_upload,
)

LOGGER = logging.getLogger(__name__)
MAX_SESSION_NAME_LENGTH = 150
MAX_SAMPLING_INTERVAL_SECONDS = 3600.0
PUBLIC_PROCESSING_FAILURE = (
    "Video processing failed. Please review the input and retry."
)


class InvalidVideoAnalysisOptionsError(ValueError):
    """Raised when video analysis options are incomplete or outside safe limits."""


@dataclass(frozen=True)
class QueuedVideoAnalysis:
    session_id: int
    status: str
    sampled_frames_total: int
    sampling_interval_seconds: float
    grid_rows: int | None
    grid_columns: int | None


@dataclass(frozen=True)
class VideoWorkItem:
    session_id: int
    path: Path
    sampling_interval_seconds: float
    grid_rows: int | None
    grid_columns: int | None


class VideoAnalysisService:
    def __init__(
        self,
        *,
        detector_provider: Callable,
        model_profile: RuntimeModelProfile,
        crowd_analysis_decision: DenseCrowdAnalysisDecision,
        upload_directory: Path,
        output_directory: Path,
        upload_policy: VideoUploadPolicy,
        max_grid_dimension: int,
        worker_count: int = 1,
        executor: Executor | None = None,
        store_upload: Callable = store_validated_video_upload,
        create_job: Callable = create_video_analysis_job,
        mark_processing: Callable = mark_video_job_processing,
        update_progress: Callable = update_video_job_progress,
        complete_job: Callable = complete_video_analysis_job,
        fail_job: Callable = fail_video_analysis_job,
        read_job: Callable = get_video_analysis_job,
        video_reader_factory: Callable = VideoReader,
        output_writer: Callable = save_image_output,
        asset_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if worker_count < 1:
            raise ValueError("Video worker count must be positive.")
        self._detector_provider = detector_provider
        self._profile = model_profile
        self._crowd_decision = crowd_analysis_decision
        self._upload_directory = Path(upload_directory)
        self._output_directory = Path(output_directory)
        self._upload_policy = upload_policy
        self._max_grid_dimension = max_grid_dimension
        self._executor = executor or ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="video-analysis"
        )
        self._store_upload = store_upload
        self._create_job = create_job
        self._mark_processing = mark_processing
        self._update_progress = update_progress
        self._complete_job = complete_job
        self._fail_job = fail_job
        self._read_job = read_job
        self._video_reader_factory = video_reader_factory
        self._output_writer = output_writer
        self._asset_id_factory = asset_id_factory
        self._stop = Event()

    def submit_upload(
        self,
        file,
        *,
        filename: str | None,
        content_type: str | None,
        session_name: str | None,
        sampling_interval_seconds: float,
        grid_rows: int | None,
        grid_columns: int | None,
    ) -> QueuedVideoAnalysis:
        session_name, sampling_interval_seconds = self._validate_options(
            session_name, sampling_interval_seconds, grid_rows, grid_columns
        )
        stored: StoredVideoUpload = self._store_upload(
            file,
            filename=filename,
            content_type=content_type,
            upload_directory=self._upload_directory,
            policy=self._upload_policy,
        )
        sampled_total = calculate_sampled_frame_count(
            stored.metadata.frame_count,
            stored.metadata.fps,
            sampling_interval_seconds,
        )
        try:
            created: CreatedVideoJob = self._create_job(
                video_path=stored.path,
                original_filename=stored.original_filename,
                session_name=session_name,
                sampling_interval_seconds=sampling_interval_seconds,
                grid_rows=grid_rows,
                grid_columns=grid_columns,
                total_source_frames=stored.metadata.frame_count,
                sampled_frames_total=sampled_total,
                model_profile=self._profile,
                crowd_analysis_decision=self._crowd_decision,
            )
        except Exception:
            stored.path.unlink(missing_ok=True)
            raise

        item = VideoWorkItem(
            session_id=created.session_id,
            path=stored.path,
            sampling_interval_seconds=sampling_interval_seconds,
            grid_rows=grid_rows,
            grid_columns=grid_columns,
        )
        try:
            self._executor.submit(self._process, item)
        except Exception:
            self._fail_job(
                created.session_id,
                "worker_unavailable",
                "The video worker is unavailable. Please retry the upload.",
            )
            raise
        return QueuedVideoAnalysis(
            session_id=created.session_id,
            status="queued",
            sampled_frames_total=sampled_total,
            sampling_interval_seconds=sampling_interval_seconds,
            grid_rows=grid_rows,
            grid_columns=grid_columns,
        )

    def get_job(self, session_id: int):
        return self._read_job(session_id)

    def close(self) -> None:
        self._stop.set()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _process(self, item: VideoWorkItem) -> None:
        output_paths: list[Path] = []
        try:
            if self._stop.is_set():
                raise RuntimeError("Video worker is shutting down.")
            self._mark_processing(item.session_id)
            detector = self._detector_provider()
            results = []
            with self._video_reader_factory(item.path) as reader:
                sampled = sample_video_frames(reader, item.sampling_interval_seconds)
                for result in process_sampled_video_frames(
                    sampled, detector, self._profile
                ):
                    if self._stop.is_set():
                        raise RuntimeError("Video worker is shutting down.")
                    if item.grid_rows is not None and item.grid_columns is not None:
                        grid = count_detections_by_grid(
                            result.detection_records,
                            result.image_width,
                            result.image_height,
                            rows=item.grid_rows,
                            columns=item.grid_columns,
                        )
                        result = replace(result, grid_count_result=grid)
                    result = self._store_frame_asset(result)
                    if result.output_file_path is None:
                        raise RuntimeError("Video frame output path was not assigned.")
                    output_paths.append(result.output_file_path)
                    results.append(result)
                    self._update_progress(item.session_id, len(results))
            self._complete_job(item.session_id, results)
        except Exception:
            for output_path in output_paths:
                output_path.unlink(missing_ok=True)
            LOGGER.exception("Video analysis job %s failed", item.session_id)
            self._fail_job(
                item.session_id,
                "video_processing_failed",
                PUBLIC_PROCESSING_FAILURE,
            )

    def _store_frame_asset(self, result):
        if result.annotated_image is None:
            raise RuntimeError("Video processing did not produce an annotated frame.")
        if result.annotated_image.shape[:2] != (
            result.image_height,
            result.image_width,
        ):
            raise RuntimeError(
                "Annotated video frame dimensions do not match its metadata."
            )

        asset_id = self._asset_id_factory()
        output_path = self._output_directory / f"{asset_id}.jpg"
        try:
            self._output_writer(result.annotated_image, output_path)
        except Exception:
            output_path.unlink(missing_ok=True)
            raise
        return replace(
            result,
            output_asset_id=asset_id,
            output_file_path=output_path,
            annotated_image=None,
        )

    def _validate_options(
        self,
        session_name: str | None,
        sampling_interval_seconds: float,
        grid_rows: int | None,
        grid_columns: int | None,
    ) -> tuple[str | None, float]:
        if session_name is not None:
            session_name = session_name.strip()
            if not session_name or len(session_name) > MAX_SESSION_NAME_LENGTH:
                raise InvalidVideoAnalysisOptionsError(
                    "Session name must contain 1 to 150 characters."
                )
        if (
            isinstance(sampling_interval_seconds, bool)
            or not math.isfinite(sampling_interval_seconds)
            or not 0 < sampling_interval_seconds <= MAX_SAMPLING_INTERVAL_SECONDS
        ):
            raise InvalidVideoAnalysisOptionsError(
                "Sampling interval must be between 0 and 3600 seconds."
            )
        if (grid_rows is None) != (grid_columns is None):
            raise InvalidVideoAnalysisOptionsError(
                "Grid rows and columns must be provided together."
            )
        for value in (grid_rows, grid_columns):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= self._max_grid_dimension
            ):
                raise InvalidVideoAnalysisOptionsError(
                    "Grid dimensions must be positive and within the configured limit."
                )
        return session_name, float(sampling_interval_seconds)
