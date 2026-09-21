import logging
import math
from collections.abc import Callable, Sequence
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from time import monotonic
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
from app.logging_config import request_id_context
from app.model_profile import RuntimeModelProfile
from app.services.alert_service import (
    ThresholdAlertRule,
    evaluate_threshold_alerts,
)
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
from app.services.workload import (
    AnalysisBusyError,
    AnalysisTimeoutError,
    WorkloadAdmission,
    WorkloadLimits,
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
    submitted_at: float = 0
    request_id: str | None = None


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
        alert_rules: Sequence[ThresholdAlertRule] = (),
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
        limits: WorkloadLimits | None = None,
        admission: WorkloadAdmission | None = None,
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
        self._alert_rules = tuple(alert_rules)
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
        self._limits = limits or WorkloadLimits()
        self._admission = admission or WorkloadAdmission(
            self._limits.max_inflight_analyses
        )

    def submit_upload(
        self,
        file,
        **options,
    ) -> QueuedVideoAnalysis:
        if self._stop.is_set():
            raise AnalysisBusyError("The worker is stopping.")
        self._admission.acquire()
        try:
            return self._submit_reserved(file, **options)
        except Exception:
            self._admission.release()
            raise

    def _submit_reserved(
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
        try:
            metadata = stored.metadata
            if (
                not math.isfinite(metadata.fps)
                or metadata.fps <= 0
                or metadata.frame_count < 1
                or metadata.frame_count > self._limits.max_video_source_frames
                or metadata.frame_count / metadata.fps
                > self._limits.max_video_duration_seconds
                or int(metadata.width * self._profile.scale_factor)
                * int(metadata.height * self._profile.scale_factor)
                > self._limits.max_processed_pixels
            ):
                raise InvalidVideoAnalysisOptionsError(
                    "Video duration, frame count or processed dimensions "
                    "exceed the configured limits."
                )
            sampled_total = calculate_sampled_frame_count(
                metadata.frame_count, metadata.fps, sampling_interval_seconds
            )
            if sampled_total > self._limits.max_sampled_frames:
                raise InvalidVideoAnalysisOptionsError(
                    "Too many sampled frames. Increase the sampling interval "
                    "or use a shorter video."
                )
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
            submitted_at=monotonic(),
            request_id=request_id_context.get(),
        )
        try:
            self._executor.submit(self._process, item)
        except Exception:
            try:
                self._fail_job(
                    created.session_id,
                    "worker_unavailable",
                    "The video worker is unavailable. Please retry the upload.",
                )
            finally:
                stored.path.unlink(missing_ok=True)
            raise
        LOGGER.info(
            "video_queued",
            extra={"session_id": created.session_id, "sampled_frames": sampled_total},
        )
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
        started = monotonic()
        token = request_id_context.set(item.request_id)
        deadline = started + self._limits.max_processing_seconds
        failure_code = "video_processing_failed"

        def check_frame(frame_number=0, frame=None):
            if self._stop.is_set():
                raise AnalysisTimeoutError("Worker shutdown requested.")
            if monotonic() >= deadline:
                raise AnalysisTimeoutError("Video processing deadline exceeded.")
            if frame is not None:
                height, width = frame.shape[:2]
                if (
                    frame_number >= self._limits.max_video_source_frames
                    or frame_number / reader.metadata.fps
                    >= self._limits.max_video_duration_seconds
                    or int(width * self._profile.scale_factor)
                    * int(height * self._profile.scale_factor)
                    > self._limits.max_processed_pixels
                ):
                    raise InvalidVideoAnalysisOptionsError(
                        "Decoded video exceeds processing limits."
                    )

        try:
            if started - item.submitted_at > self._limits.max_queue_seconds:
                failure_code = "video_queue_timeout"
                raise AnalysisTimeoutError("Video queue deadline exceeded.")
            check_frame()
            self._mark_processing(item.session_id)
            detector = self._detector_provider()
            results = []
            detection_count = 0
            with self._video_reader_factory(item.path) as reader:

                def bounded_samples():
                    for index, sample in enumerate(
                        sample_video_frames(
                            reader,
                            item.sampling_interval_seconds,
                            check_frame=check_frame,
                        )
                    ):
                        if (
                            index >= self._limits.max_sampled_frames
                            or sample.timestamp_seconds
                            >= self._limits.max_video_duration_seconds
                        ):
                            raise InvalidVideoAnalysisOptionsError(
                                "Decoded video exceeds sample or duration limits."
                            )
                        yield sample

                for result in process_sampled_video_frames(
                    bounded_samples(), detector, self._profile
                ):
                    check_frame()
                    detection_count += len(result.detection_records)
                    if (
                        len(results) >= self._limits.max_sampled_frames
                        or detection_count > self._limits.max_video_detection_records
                    ):
                        raise InvalidVideoAnalysisOptionsError(
                            "Video result storage budget exceeded."
                        )
                    if item.grid_rows is not None and item.grid_columns is not None:
                        grid = count_detections_by_grid(
                            result.detection_records,
                            result.image_width,
                            result.image_height,
                            rows=item.grid_rows,
                            columns=item.grid_columns,
                        )
                        result = replace(result, grid_count_result=grid)
                    alerts = evaluate_threshold_alerts(
                        self._alert_rules,
                        frame_object_counts=result.object_counts,
                        grid_count_result=result.grid_count_result,
                    )
                    result = replace(result, alert_records=alerts)
                    result = self._store_frame_asset(result)
                    if result.output_file_path is None:
                        raise RuntimeError("Video frame output path was not assigned.")
                    output_paths.append(result.output_file_path)
                    results.append(result)
                    self._update_progress(item.session_id, len(results))
            check_frame()
            self._complete_job(item.session_id, results)
            LOGGER.info(
                "video_completed",
                extra={
                    "session_id": item.session_id,
                    "sampled_frames": len(results),
                    "duration_seconds": round(monotonic() - started, 6),
                },
            )
        except Exception as error:
            if (
                isinstance(error, AnalysisTimeoutError)
                and failure_code != "video_queue_timeout"
            ):
                failure_code = (
                    "worker_interrupted"
                    if self._stop.is_set()
                    else "video_processing_timeout"
                )
            elif isinstance(error, InvalidVideoAnalysisOptionsError):
                failure_code = "video_limit_exceeded"
            for output_path in output_paths:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError:
                    LOGGER.exception(
                        "video_partial_cleanup_failed",
                        extra={"session_id": item.session_id},
                    )
            LOGGER.exception(
                "video_failed",
                extra={
                    "session_id": item.session_id,
                    "failure_code": failure_code,
                    "duration_seconds": round(monotonic() - started, 6),
                },
            )
            try:
                self._fail_job(
                    item.session_id,
                    failure_code,
                    PUBLIC_PROCESSING_FAILURE,
                )
            except Exception:
                LOGGER.exception(
                    "video_failure_recording_failed",
                    extra={"session_id": item.session_id},
                )
                raise
        finally:
            request_id_context.reset(token)
            self._admission.release()

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
            or not self._limits.min_sampling_interval_seconds
            <= sampling_interval_seconds
            <= MAX_SAMPLING_INTERVAL_SECONDS
        ):
            raise InvalidVideoAnalysisOptionsError(
                "Sampling interval must be between "
                f"{self._limits.min_sampling_interval_seconds} and 3600 seconds."
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
