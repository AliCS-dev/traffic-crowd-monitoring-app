import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation.evaluation_config import (
    DATASET_ROLES,
    PROJECT_CLASSES,
    ClassMapping,
    DatasetSettings,
)

ANNOTATION_TYPES = ("bounding_box", "point_count")
MANIFEST_FIELDS = {
    "asset_id",
    "dataset_version",
    "collection_id",
    "source_group_id",
    "dataset_role",
    "evaluation_image_path",
    "width",
    "height",
    "target_classes",
    "annotation_type",
    "canonical_annotation_path",
}


class EvaluationDataError(ValueError):
    """Raised when selected evaluation data cannot be loaded consistently."""


@dataclass(frozen=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Bounding-box width and height must be positive")

    @classmethod
    def from_xyxy(
        cls, x_min: float, y_min: float, x_max: float, y_max: float
    ) -> "BoundingBox":
        return cls(x_min, y_min, x_max - x_min, y_max - y_min)

    def as_xywh(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.width, self.height

    def as_xyxy(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.x + self.width, self.y + self.height

    def to_original_coordinates(
        self, scale_factor: int, image_width: int, image_height: int
    ) -> "BoundingBox":
        if scale_factor < 1:
            raise ValueError("Scale factor must be at least 1")
        if image_width < 1 or image_height < 1:
            raise ValueError("Image dimensions must be positive")

        x_min, y_min, x_max, y_max = (value / scale_factor for value in self.as_xyxy())
        x_min = min(max(x_min, 0.0), float(image_width))
        y_min = min(max(y_min, 0.0), float(image_height))
        x_max = min(max(x_max, 0.0), float(image_width))
        y_max = min(max(y_max, 0.0), float(image_height))
        return BoundingBox.from_xyxy(x_min, y_min, x_max, y_max)


@dataclass(frozen=True)
class EvaluationAsset:
    asset_id: str
    collection_id: str
    source_group_id: str
    dataset_role: str
    image_path: Path
    width: int
    height: int
    annotation_type: str
    target_classes: frozenset[str]

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("Evaluation asset ID must not be empty")
        if self.width < 1 or self.height < 1:
            raise ValueError("Evaluation asset dimensions must be positive")
        if self.dataset_role not in DATASET_ROLES:
            raise ValueError(f"Unknown dataset role: {self.dataset_role}")
        if self.annotation_type not in ANNOTATION_TYPES:
            raise ValueError(f"Unknown annotation type: {self.annotation_type}")
        unknown = self.target_classes - set(PROJECT_CLASSES)
        if unknown:
            raise ValueError(
                "Evaluation asset has unknown target classes: "
                f"{', '.join(sorted(unknown))}"
            )

    def includes_class(self, project_class: str | None) -> bool:
        return project_class is not None and project_class in self.target_classes


@dataclass(frozen=True)
class GroundTruthBox:
    asset_id: str
    project_class: str
    box: BoundingBox

    def __post_init__(self) -> None:
        if self.project_class not in PROJECT_CLASSES:
            raise ValueError(f"Unknown ground-truth class: {self.project_class}")


@dataclass(frozen=True)
class CountReference:
    asset_id: str
    project_class: str
    count: int

    def __post_init__(self) -> None:
        if self.project_class not in PROJECT_CLASSES:
            raise ValueError(f"Unknown count-reference class: {self.project_class}")
        if self.count < 0:
            raise ValueError("Count reference must not be negative")


@dataclass(frozen=True)
class PredictionRecord:
    asset_id: str
    source_class: str
    project_class: str | None
    confidence: float
    box: BoundingBox

    def __post_init__(self) -> None:
        if self.project_class is not None and self.project_class not in PROJECT_CLASSES:
            raise ValueError(f"Unknown prediction class: {self.project_class}")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Prediction confidence must be between 0 and 1")


@dataclass(frozen=True)
class EvaluationDataset:
    role: str
    version: str
    assets: tuple[EvaluationAsset, ...]
    ground_truth_boxes: tuple[GroundTruthBox, ...]
    count_references: tuple[CountReference, ...]

    def __post_init__(self) -> None:
        asset_ids = [asset.asset_id for asset in self.assets]
        if not asset_ids:
            raise EvaluationDataError("Selected evaluation dataset is empty")
        if len(asset_ids) != len(set(asset_ids)):
            raise EvaluationDataError("Evaluation dataset contains duplicate asset IDs")

        known_assets = set(asset_ids)
        referenced_assets = {
            item.asset_id for item in (*self.ground_truth_boxes, *self.count_references)
        }
        unknown_assets = referenced_assets - known_assets
        if unknown_assets:
            raise EvaluationDataError(
                "Annotations reference unknown assets: "
                f"{', '.join(sorted(unknown_assets))}"
            )

    def asset_by_id(self) -> dict[str, EvaluationAsset]:
        return {asset.asset_id: asset for asset in self.assets}


def parse_target_classes(value: str) -> frozenset[str]:
    classes = frozenset(item.strip() for item in value.split(";") if item.strip())
    if not classes:
        raise ValueError("At least one target class is required")
    unknown = classes - set(PROJECT_CLASSES)
    if unknown:
        raise ValueError(f"Unknown target classes: {', '.join(sorted(unknown))}")
    return classes


def create_prediction_record(
    *,
    asset: EvaluationAsset,
    source_class: str,
    confidence: float,
    processed_box: BoundingBox,
    scale_factor: int,
    class_mapping: ClassMapping,
) -> PredictionRecord:
    return PredictionRecord(
        asset_id=asset.asset_id,
        source_class=source_class,
        project_class=class_mapping.map(source_class),
        confidence=confidence,
        box=processed_box.to_original_coordinates(
            scale_factor, asset.width, asset.height
        ),
    )


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)
    except FileNotFoundError as error:
        raise EvaluationDataError(f"Evaluation data file not found: {path}") from error


def _read_json(path: Path) -> dict[str, Any]:
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EvaluationDataError(f"Evaluation data file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise EvaluationDataError(f"Evaluation JSON is invalid: {path}") from error
    if not isinstance(values, dict):
        raise EvaluationDataError(f"Evaluation JSON must contain an object: {path}")
    return values


def _repository_path(repository_root: Path, value: str, field: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise EvaluationDataError(f"{field} must be relative to the repository")
    return repository_root / path


def _parse_dimension(value: str, asset_id: str, field: str) -> int:
    try:
        dimension = int(value)
    except ValueError as error:
        raise EvaluationDataError(
            f"Asset {asset_id} has an invalid {field}: {value!r}"
        ) from error
    if dimension < 1:
        raise EvaluationDataError(f"Asset {asset_id} has a non-positive {field}")
    return dimension


def _load_manifest_assets(
    repository_root: Path, settings: DatasetSettings
) -> tuple[list[EvaluationAsset], list[dict[str, str]]]:
    manifest_path = repository_root / settings.manifest_path
    fields, rows = _read_csv(manifest_path)
    missing_fields = MANIFEST_FIELDS - set(fields)
    if missing_fields:
        raise EvaluationDataError(
            "Evaluation manifest is missing fields: "
            f"{', '.join(sorted(missing_fields))}"
        )

    selected_rows = [row for row in rows if row["dataset_role"] == settings.role]
    if not selected_rows:
        raise EvaluationDataError(
            f"Evaluation manifest contains no assets for role: {settings.role}"
        )

    assets = []
    for row in selected_rows:
        asset_id = row["asset_id"]
        if row["dataset_version"] != settings.version:
            raise EvaluationDataError(
                f"Asset {asset_id} uses dataset version {row['dataset_version']!r}; "
                f"expected {settings.version!r}"
            )
        assets.append(
            EvaluationAsset(
                asset_id=asset_id,
                collection_id=row["collection_id"],
                source_group_id=row["source_group_id"],
                dataset_role=row["dataset_role"],
                image_path=_repository_path(
                    repository_root,
                    row["evaluation_image_path"],
                    "evaluation_image_path",
                ),
                width=_parse_dimension(row["width"], asset_id, "width"),
                height=_parse_dimension(row["height"], asset_id, "height"),
                annotation_type=row["annotation_type"],
                target_classes=parse_target_classes(row["target_classes"]),
            )
        )
    return assets, selected_rows


def _category_lookup(values: dict[str, Any], path: Path) -> dict[int, str]:
    categories = values.get("categories")
    if not isinstance(categories, list):
        raise EvaluationDataError(f"COCO categories are missing or invalid: {path}")
    lookup = {}
    for category in categories:
        if not isinstance(category, dict):
            raise EvaluationDataError(f"COCO category is invalid: {path}")
        category_id = category.get("id")
        name = category.get("name")
        if not isinstance(category_id, int) or name not in PROJECT_CLASSES:
            raise EvaluationDataError(f"COCO category is unknown or invalid: {path}")
        lookup[category_id] = name
    return lookup


def _load_coco_boxes(
    path: Path,
    expected_asset_ids: set[str],
    assets: dict[str, EvaluationAsset],
) -> list[GroundTruthBox]:
    values = _read_json(path)
    categories = _category_lookup(values, path)
    images = values.get("images")
    annotations = values.get("annotations")
    if not isinstance(images, list) or not isinstance(annotations, list):
        raise EvaluationDataError(f"COCO images or annotations are invalid: {path}")

    image_assets = {}
    for image in images:
        if not isinstance(image, dict):
            raise EvaluationDataError(f"COCO image record is invalid: {path}")
        image_id = image.get("id")
        asset_id = image.get("asset_id")
        if not isinstance(image_id, int) or not isinstance(asset_id, str):
            raise EvaluationDataError(f"COCO image identity is invalid: {path}")
        if image_id in image_assets:
            raise EvaluationDataError(f"COCO image IDs are duplicated: {path}")
        image_assets[image_id] = asset_id

    actual_asset_ids = set(image_assets.values())
    if actual_asset_ids != expected_asset_ids:
        raise EvaluationDataError(
            f"COCO image membership does not match the selected manifest: {path}"
        )

    boxes = []
    for annotation in annotations:
        if not isinstance(annotation, dict):
            raise EvaluationDataError(f"COCO annotation is invalid: {path}")
        asset_id = image_assets.get(annotation.get("image_id"))
        project_class = categories.get(annotation.get("category_id"))
        bbox = annotation.get("bbox")
        if asset_id is None or project_class is None:
            raise EvaluationDataError(f"COCO annotation reference is invalid: {path}")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise EvaluationDataError(f"COCO bounding box is invalid: {path}")
        try:
            box = BoundingBox(*(float(value) for value in bbox))
        except (TypeError, ValueError) as error:
            raise EvaluationDataError(
                f"COCO bounding box is invalid: {path}"
            ) from error
        if not assets[asset_id].includes_class(project_class):
            continue
        boxes.append(
            GroundTruthBox(
                asset_id=asset_id,
                project_class=project_class,
                box=box,
            )
        )
    return boxes


def _load_count_references(
    path: Path, expected_asset_ids: set[str]
) -> list[CountReference]:
    fields, rows = _read_csv(path)
    required_fields = {"asset_id", "dataset_role", "person_count"}
    if not required_fields.issubset(fields):
        raise EvaluationDataError(f"Count-reference fields are invalid: {path}")
    selected_rows = [row for row in rows if row["asset_id"] in expected_asset_ids]
    actual_asset_ids = {row["asset_id"] for row in selected_rows}
    if actual_asset_ids != expected_asset_ids:
        raise EvaluationDataError(
            f"Count-reference membership does not match the selected manifest: {path}"
        )

    references = []
    for row in selected_rows:
        try:
            count = int(row["person_count"])
        except ValueError as error:
            raise EvaluationDataError(
                f"Count reference is invalid for {row['asset_id']}"
            ) from error
        references.append(
            CountReference(
                asset_id=row["asset_id"], project_class="person", count=count
            )
        )
    return references


def load_evaluation_dataset(
    repository_root: Path, settings: DatasetSettings
) -> EvaluationDataset:
    repository_root = repository_root.resolve()
    assets, rows = _load_manifest_assets(repository_root, settings)
    asset_lookup = {asset.asset_id: asset for asset in assets}
    annotation_groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        annotation_path = row["canonical_annotation_path"]
        if not annotation_path:
            raise EvaluationDataError(
                f"Asset {row['asset_id']} has no canonical annotation path"
            )
        annotation_groups[(row["annotation_type"], annotation_path)].add(
            row["asset_id"]
        )

    boxes = []
    references = []
    for (annotation_type, relative_path), asset_ids in sorted(
        annotation_groups.items()
    ):
        path = _repository_path(
            repository_root, relative_path, "canonical_annotation_path"
        )
        if annotation_type == "bounding_box":
            boxes.extend(_load_coco_boxes(path, asset_ids, asset_lookup))
        elif annotation_type == "point_count":
            references.extend(_load_count_references(path, asset_ids))
        else:
            raise EvaluationDataError(f"Unknown annotation type: {annotation_type}")

    return EvaluationDataset(
        role=settings.role,
        version=settings.version,
        assets=tuple(assets),
        ground_truth_boxes=tuple(boxes),
        count_references=tuple(references),
    )
