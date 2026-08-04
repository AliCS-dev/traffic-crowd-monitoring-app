from dataclasses import dataclass
from typing import Protocol

from app.services.detection_service import extract_detection_records
from app.services.image_service import load_input_image
from app.services.preprocessing_service import preprocess_image_for_detection
from evaluation.evaluation_config import EvaluationConfig
from evaluation.evaluation_data import (
    BoundingBox,
    EvaluationAsset,
    EvaluationDataset,
    PredictionRecord,
    create_prediction_record,
)


class EvaluationRunnerError(RuntimeError):
    """Raised when model inference cannot produce a valid evaluation record."""


class Detector(Protocol):
    def detect(
        self,
        image,
        confidence_threshold: float,
        image_size: int,
        *,
        device: str,
        max_detections: int,
        half_precision: bool,
        verbose: bool,
    ): ...


@dataclass(frozen=True)
class PredictionBatch:
    asset_ids: tuple[str, ...]
    predictions: tuple[PredictionRecord, ...]

    @property
    def processed_assets(self) -> int:
        return len(self.asset_ids)


def validate_dataset_configuration(
    dataset: EvaluationDataset, config: EvaluationConfig
) -> None:
    if dataset.role != config.dataset.role:
        raise EvaluationRunnerError(
            f"Loaded dataset role {dataset.role!r} does not match configured role "
            f"{config.dataset.role!r}"
        )
    if dataset.version != config.dataset.version:
        raise EvaluationRunnerError(
            f"Loaded dataset version {dataset.version!r} does not match configured "
            f"version {config.dataset.version!r}"
        )


def _validate_image_dimensions(asset_id: str, image, width: int, height: int) -> None:
    actual_height, actual_width = image.shape[:2]
    if (actual_width, actual_height) != (width, height):
        raise EvaluationRunnerError(
            f"Asset {asset_id} has dimensions {actual_width}x{actual_height}; "
            f"the manifest records {width}x{height}"
        )


def _prediction_from_record(
    record: dict,
    *,
    asset,
    config: EvaluationConfig,
) -> PredictionRecord:
    try:
        processed_box = BoundingBox.from_xyxy(
            record["bbox_x_min"],
            record["bbox_y_min"],
            record["bbox_x_max"],
            record["bbox_y_max"],
        )
        return create_prediction_record(
            asset=asset,
            source_class=record["object_class"],
            confidence=record["confidence"],
            processed_box=processed_box,
            scale_factor=config.inference.scale_factor,
            class_mapping=config.model.class_mapping,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EvaluationRunnerError(
            f"Detector returned an invalid prediction for asset {asset.asset_id}"
        ) from error


def load_evaluation_image(asset: EvaluationAsset):
    image = load_input_image(asset.image_path)
    _validate_image_dimensions(asset.asset_id, image, asset.width, asset.height)
    return image


def preprocess_evaluation_image(image, config: EvaluationConfig):
    return preprocess_image_for_detection(
        image, scale_factor=config.inference.scale_factor
    )


def detect_evaluation_image(
    asset_id: str,
    processed_image,
    detector: Detector,
    config: EvaluationConfig,
):
    results = detector.detect(
        processed_image,
        confidence_threshold=config.inference.confidence_floor,
        image_size=config.inference.image_size,
        device=config.inference.device,
        max_detections=config.inference.max_detections,
        half_precision=config.inference.numeric_precision == "float16",
        verbose=False,
    )
    if not results:
        raise EvaluationRunnerError(f"Detector produced no result for asset {asset_id}")
    if len(results) != 1:
        raise EvaluationRunnerError(
            f"Detector produced {len(results)} results for asset {asset_id}; "
            "expected one"
        )
    return results[0]


def convert_evaluation_result(
    result,
    asset: EvaluationAsset,
    config: EvaluationConfig,
) -> tuple[PredictionRecord, ...]:
    return tuple(
        _prediction_from_record(record, asset=asset, config=config)
        for record in extract_detection_records(result)
    )


def generate_predictions(
    dataset: EvaluationDataset,
    detector: Detector,
    config: EvaluationConfig,
) -> PredictionBatch:
    validate_dataset_configuration(dataset, config)

    asset_ids = []
    predictions = []
    for asset in dataset.assets:
        image = load_evaluation_image(asset)
        processed_image = preprocess_evaluation_image(image, config)
        result = detect_evaluation_image(
            asset.asset_id, processed_image, detector, config
        )
        predictions.extend(convert_evaluation_result(result, asset, config))
        asset_ids.append(asset.asset_id)

    return PredictionBatch(tuple(asset_ids), tuple(predictions))
