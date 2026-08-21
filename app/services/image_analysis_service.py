from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import BinaryIO
from uuid import UUID, uuid4

from app.crowd_analysis import DenseCrowdAnalysisDecision
from app.database.detection_repository import save_image_detection_results
from app.model_profile import RuntimeModelProfile
from app.services.alert_service import (
    ThresholdAlertRule,
    evaluate_threshold_alerts,
)
from app.services.detection_service import (
    build_object_count_summary_records,
    count_detected_objects,
    detect_objects_with_profile,
    extract_detection_records,
)
from app.services.grid_counting_service import count_detections_by_grid
from app.services.image_upload_service import (
    ImageUploadPolicy,
    validate_image_upload,
)
from app.services.output_service import save_detection_output
from app.services.preprocessing_service import preprocess_image_for_detection


class InvalidImageAnalysisOptionsError(ValueError):
    """Raised when image session or grid options are invalid."""


@dataclass(frozen=True)
class ImageAnalysisResult:
    session_id: int
    output_asset_id: UUID
    detection_count: int
    grid_rows: int | None
    grid_columns: int | None
    dense_crowd_analysis: DenseCrowdAnalysisDecision


class ImageAnalysisService:
    def __init__(
        self,
        *,
        detector,
        model_profile: RuntimeModelProfile,
        crowd_analysis_decision: DenseCrowdAnalysisDecision,
        upload_directory: Path,
        output_directory: Path,
        upload_policy: ImageUploadPolicy,
        max_grid_dimension: int,
        alert_rules: Sequence[ThresholdAlertRule] = (),
        persistence_function: Callable = save_image_detection_results,
        asset_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if max_grid_dimension < 1:
            raise ValueError("Maximum grid dimension must be positive.")
        self._detector = detector
        self._model_profile = model_profile
        self._crowd_analysis_decision = crowd_analysis_decision
        self._upload_directory = Path(upload_directory)
        self._output_directory = Path(output_directory)
        self._upload_policy = upload_policy
        self._max_grid_dimension = max_grid_dimension
        self._alert_rules = tuple(alert_rules)
        self._persistence_function = persistence_function
        self._asset_id_factory = asset_id_factory
        self._analysis_lock = Lock()

    def analyze_upload(
        self,
        file: BinaryIO,
        *,
        filename: str | None,
        content_type: str | None,
        session_name: str | None = None,
        grid_rows: int | None = None,
        grid_columns: int | None = None,
    ) -> ImageAnalysisResult:
        session_name = _validate_session_name(session_name)
        _validate_grid_options(
            grid_rows,
            grid_columns,
            max_dimension=self._max_grid_dimension,
        )
        upload = validate_image_upload(
            file,
            filename=filename,
            content_type=content_type,
            policy=self._upload_policy,
        )

        with self._analysis_lock:
            return self._analyze_validated_upload(
                upload,
                session_name=session_name,
                grid_rows=grid_rows,
                grid_columns=grid_columns,
            )

    def _analyze_validated_upload(
        self,
        upload,
        *,
        session_name,
        grid_rows,
        grid_columns,
    ) -> ImageAnalysisResult:
        asset_id = self._asset_id_factory()
        input_path = self._upload_directory / f"{asset_id}{upload.suffix}"
        output_path = self._output_directory / f"{asset_id}.jpg"
        persisted = False

        try:
            self._upload_directory.mkdir(parents=True, exist_ok=True)
            self._output_directory.mkdir(parents=True, exist_ok=True)
            with input_path.open("xb") as handle:
                handle.write(upload.content)

            processed_image = preprocess_image_for_detection(
                upload.image,
                scale_factor=self._model_profile.scale_factor,
            )
            results = detect_objects_with_profile(
                processed_image,
                self._detector,
                self._model_profile,
            )
            if not results:
                raise RuntimeError("Image detection returned no result object.")

            first_result = results[0]
            class_mapping = self._model_profile.class_mapping_dict()
            object_counts = count_detected_objects(first_result, class_mapping)
            detection_records = extract_detection_records(first_result, class_mapping)
            processed_height, processed_width = processed_image.shape[:2]

            grid_result = None
            if grid_rows is not None and grid_columns is not None:
                grid_result = count_detections_by_grid(
                    detection_records,
                    image_width=processed_width,
                    image_height=processed_height,
                    rows=grid_rows,
                    columns=grid_columns,
                )

            alert_records = evaluate_threshold_alerts(
                self._alert_rules,
                frame_object_counts=object_counts,
                grid_count_result=grid_result,
            )

            save_detection_output(
                first_result,
                output_path,
                expected_width=processed_width,
                expected_height=processed_height,
            )
            stored_result = self._persistence_function(
                image_path=input_path,
                image_width=processed_width,
                image_height=processed_height,
                detection_records=detection_records,
                object_count_summary_records=build_object_count_summary_records(
                    object_counts
                ),
                grid_count_result=grid_result,
                alert_records=alert_records,
                session_name=session_name,
                model_profile=self._model_profile,
                crowd_analysis_decision=self._crowd_analysis_decision,
                original_filename=upload.original_filename,
                output_asset_id=asset_id,
                output_file_path=output_path,
            )
            persisted = True
            return ImageAnalysisResult(
                session_id=stored_result["session_id"],
                output_asset_id=asset_id,
                detection_count=len(detection_records),
                grid_rows=grid_rows,
                grid_columns=grid_columns,
                dense_crowd_analysis=self._crowd_analysis_decision,
            )
        finally:
            if not persisted:
                input_path.unlink(missing_ok=True)
                output_path.unlink(missing_ok=True)


def _validate_session_name(session_name: str | None) -> str | None:
    if session_name is None:
        return None
    session_name = session_name.strip()
    if not session_name:
        return None
    if len(session_name) > 150:
        raise InvalidImageAnalysisOptionsError(
            "Session name must contain at most 150 characters."
        )
    return session_name


def _validate_grid_options(grid_rows, grid_columns, *, max_dimension: int) -> None:
    if grid_rows is None and grid_columns is None:
        return
    if grid_rows is None or grid_columns is None:
        raise InvalidImageAnalysisOptionsError(
            "Grid rows and columns must be provided together."
        )
    for name, value in (("rows", grid_rows), ("columns", grid_columns)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidImageAnalysisOptionsError(
                f"Grid {name} must be a positive integer."
            )
        if not 1 <= value <= max_dimension:
            raise InvalidImageAnalysisOptionsError(
                f"Grid {name} must be between 1 and {max_dimension}."
            )
