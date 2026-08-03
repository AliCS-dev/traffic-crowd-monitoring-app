from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from evaluation.dataset_selection import exclusion_ids, sha256

ANNOTATION_MEMBER = "annotations/instances_default.json"
METADATA_FIELDS = {
    "annotation_set_id",
    "archive_path",
    "archive_sha256",
    "annotation_sha256",
    "exported_on",
    "tool",
    "format",
    "review_status",
    "notes",
}
CORRECTION_FIELDS = {
    "annotation_set_id",
    "source_annotation_id",
    "action",
    "replacement_category",
    "reviewed_on",
    "reason",
}
CORRECTION_REQUIRED_FIELDS = CORRECTION_FIELDS - {"replacement_category"}


@dataclass(frozen=True)
class ImportedManualBox:
    category_name: str
    bbox: tuple[float, float, float, float]
    source_annotation_id: int
    source_rotation_degrees: float


@dataclass
class ManualImportResult:
    annotation_set_id: str
    archive_path: str
    archive_sha256: str
    annotation_sha256: str
    source_images: int
    retained_images: int
    excluded_images: int
    retained_boxes: int
    excluded_boxes: int
    removed_duplicate_boxes: int
    relabeled_boxes: int
    classes: dict[str, int]
    roles: dict[str, dict[str, int]]
    boxes_by_asset: dict[str, list[ImportedManualBox]]

    def report_dict(self) -> dict[str, Any]:
        report = asdict(self)
        report.pop("boxes_by_asset")
        return report


def read_metadata(path: Path, annotation_set_id: str) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if set(reader.fieldnames or []) != METADATA_FIELDS:
            raise ValueError("Manual annotation export metadata fields are invalid")
        matches = [
            row for row in reader if row["annotation_set_id"] == annotation_set_id
        ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected one metadata row for {annotation_set_id}; found {len(matches)}"
        )
    row = matches[0]
    if any(not row[field] for field in METADATA_FIELDS):
        raise ValueError(f"Incomplete export metadata for {annotation_set_id}")
    return row


def read_corrections(path: Path, annotation_set_id: str) -> dict[int, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if set(reader.fieldnames or []) != CORRECTION_FIELDS:
            raise ValueError("Manual annotation correction fields are invalid")
        rows = [row for row in reader if row["annotation_set_id"] == annotation_set_id]

    corrections: dict[int, dict[str, str]] = {}
    for row in rows:
        if any(not row[field] for field in CORRECTION_REQUIRED_FIELDS):
            raise ValueError("Manual annotation correction row is incomplete")
        try:
            source_id = int(row["source_annotation_id"])
        except ValueError as error:
            raise ValueError(
                "Manual correction annotation ID must be an integer"
            ) from error
        if source_id in corrections:
            raise ValueError(f"Duplicate correction for annotation {source_id}")
        if row["action"] not in {"remove_duplicate", "relabel"}:
            raise ValueError(f"Unsupported manual correction action: {row['action']}")
        if row["action"] == "remove_duplicate" and row["replacement_category"]:
            raise ValueError("Duplicate removal cannot have a replacement category")
        if row["action"] == "relabel" and not row["replacement_category"]:
            raise ValueError("Relabel correction requires a replacement category")
        corrections[source_id] = row
    return corrections


def archive_path(repository_root: Path, relative_path: str) -> Path:
    root = repository_root.resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "Manual annotation archive must be inside the repository"
        ) from error
    return path


def load_coco_archive(
    repository_root: Path, metadata: dict[str, str]
) -> tuple[dict[str, Any], bytes]:
    path = archive_path(repository_root, metadata["archive_path"])
    if not path.is_file():
        raise FileNotFoundError(f"Missing reviewed annotation archive: {path}")
    if sha256(path) != metadata["archive_sha256"]:
        raise ValueError("Reviewed annotation archive SHA-256 does not match metadata")

    try:
        with ZipFile(path) as archive:
            annotation_bytes = archive.read(ANNOTATION_MEMBER)
    except (BadZipFile, KeyError) as error:
        raise ValueError(
            f"Reviewed archive must contain {ANNOTATION_MEMBER}"
        ) from error

    annotation_hash = hashlib.sha256(annotation_bytes).hexdigest()
    if annotation_hash != metadata["annotation_sha256"]:
        raise ValueError("Reviewed annotation JSON SHA-256 does not match metadata")
    return json.loads(annotation_bytes), annotation_bytes


def expected_filename(record: dict[str, str]) -> str:
    suffix = Path(record["evaluation_image_path"]).suffix.lower()
    return f"{record['asset_id']}{suffix}"


def validate_categories(
    categories: list[dict[str, Any]], expected_names: set[str]
) -> dict[int, str]:
    category_ids = [category.get("id") for category in categories]
    category_names = [category.get("name") for category in categories]
    if len(category_ids) != len(set(category_ids)):
        raise ValueError("Reviewed annotations contain duplicate category IDs")
    if len(category_names) != len(set(category_names)):
        raise ValueError("Reviewed annotations contain duplicate category names")
    if set(category_names) != expected_names:
        raise ValueError(
            "Reviewed annotation categories do not match project categories"
        )
    return {int(category["id"]): str(category["name"]) for category in categories}


def validated_bbox(
    annotation: dict[str, Any], width: int, height: int
) -> tuple[tuple[float, float, float, float], float]:
    bbox = annotation.get("bbox", [])
    if len(bbox) != 4:
        raise ValueError(
            f"Manual annotation {annotation.get('id')} has a malformed box"
        )
    x, y, box_width, box_height = map(float, bbox)
    if not all(math.isfinite(value) for value in (x, y, box_width, box_height)):
        raise ValueError(f"Manual annotation {annotation.get('id')} is not finite")
    if box_width <= 0 or box_height <= 0:
        raise ValueError(
            f"Manual annotation {annotation.get('id')} has non-positive area"
        )
    if int(annotation.get("iscrowd", 0)) != 0:
        raise ValueError(
            f"Manual annotation {annotation.get('id')} unexpectedly uses iscrowd"
        )

    rotation = float(annotation.get("attributes", {}).get("rotation", 0) or 0)
    if not math.isfinite(rotation):
        raise ValueError(
            f"Manual annotation {annotation.get('id')} has invalid rotation"
        )
    angle = math.radians(rotation)
    envelope_width = abs(box_width * math.cos(angle)) + abs(
        box_height * math.sin(angle)
    )
    envelope_height = abs(box_width * math.sin(angle)) + abs(
        box_height * math.cos(angle)
    )
    center_x = x + box_width / 2
    center_y = y + box_height / 2
    if not (0 <= center_x <= width and 0 <= center_y <= height):
        raise ValueError(
            f"Manual annotation {annotation.get('id')} has its centre outside the image"
        )

    x_min = max(0.0, center_x - envelope_width / 2)
    y_min = max(0.0, center_y - envelope_height / 2)
    x_max = min(float(width), center_x + envelope_width / 2)
    y_max = min(float(height), center_y + envelope_height / 2)
    if x_max <= x_min or y_max <= y_min:
        raise ValueError(
            f"Manual annotation {annotation.get('id')} has no visible image area"
        )
    return (x_min, y_min, x_max - x_min, y_max - y_min), rotation


def import_reviewed_annotations(
    repository_root: Path,
    records: list[dict[str, str]],
    metadata_path: Path,
    exclusions_path: Path,
    project_category_names: set[str],
    annotation_set_id: str = "wikimedia_manual_v1",
    corrections_path: Path | None = None,
) -> ManualImportResult:
    metadata = read_metadata(metadata_path, annotation_set_id)
    data, _ = load_coco_archive(repository_root, metadata)
    category_names = validate_categories(
        data.get("categories", []), project_category_names
    )
    corrections = (
        read_corrections(corrections_path, annotation_set_id)
        if corrections_path is not None
        else {}
    )

    retained_records = {
        expected_filename(record): record
        for record in records
        if record["annotation_type"] == "bounding_box"
        and not record["annotation_source_path"]
    }
    excluded = exclusion_ids(exclusions_path)
    excluded_filenames = {
        f"{asset_id}{Path(image.get('file_name', '')).suffix.lower()}"
        for image in data.get("images", [])
        for asset_id in [Path(str(image.get("file_name", ""))).stem]
        if asset_id in excluded
    }

    source_images = data.get("images", [])
    image_ids = [image.get("id") for image in source_images]
    filenames = [Path(str(image.get("file_name", ""))).name for image in source_images]
    if len(image_ids) != len(set(image_ids)):
        raise ValueError("Reviewed annotations contain duplicate image IDs")
    if len(filenames) != len(set(filenames)):
        raise ValueError("Reviewed annotations contain duplicate filenames")

    expected_names = set(retained_records)
    source_names = set(filenames)
    if expected_names - source_names:
        raise ValueError(
            "Reviewed archive is missing retained images: "
            + ", ".join(sorted(expected_names - source_names))
        )
    unexpected = source_names - expected_names - excluded_filenames
    if unexpected:
        raise ValueError(
            "Reviewed archive contains untracked images: "
            + ", ".join(sorted(unexpected))
        )

    source_by_id = {image["id"]: image for image in source_images}
    retained_by_image_id: dict[int, dict[str, str]] = {}
    for image in source_images:
        filename = Path(str(image["file_name"])).name
        record = retained_records.get(filename)
        if record is None:
            continue
        if (int(image["width"]), int(image["height"])) != (
            int(record["width"]),
            int(record["height"]),
        ):
            raise ValueError(f"Reviewed image dimensions do not match: {filename}")
        retained_by_image_id[int(image["id"])] = record

    annotation_ids = [
        annotation.get("id") for annotation in data.get("annotations", [])
    ]
    if len(annotation_ids) != len(set(annotation_ids)):
        raise ValueError("Reviewed annotations contain duplicate annotation IDs")

    boxes_by_asset: dict[str, list[ImportedManualBox]] = defaultdict(list)
    class_counts: Counter[str] = Counter()
    role_images: Counter[str] = Counter()
    role_boxes: Counter[str] = Counter()
    excluded_boxes = 0
    applied_corrections: set[int] = set()

    for record in retained_by_image_id.values():
        role_images[record["dataset_role"]] += 1

    for annotation in data.get("annotations", []):
        image_id = annotation.get("image_id")
        if image_id not in source_by_id:
            raise ValueError(
                f"Manual annotation {annotation.get('id')} references an unknown image"
            )
        if image_id not in retained_by_image_id:
            if annotation.get("id") in corrections:
                raise ValueError(
                    "Manual correction targets excluded annotation "
                    f"{annotation.get('id')}"
                )
            excluded_boxes += 1
            continue
        source_annotation_id = int(annotation["id"])
        correction = corrections.get(source_annotation_id)
        if correction and correction["action"] == "remove_duplicate":
            applied_corrections.add(source_annotation_id)
            continue
        try:
            category_name = category_names[int(annotation["category_id"])]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Manual annotation {annotation.get('id')} has an unknown category"
            ) from error
        if correction:
            replacement = correction["replacement_category"]
            if replacement not in project_category_names:
                raise ValueError(
                    f"Manual correction uses unknown category: {replacement}"
                )
            if replacement == category_name:
                raise ValueError(
                    "Manual correction does not change annotation "
                    f"{source_annotation_id}"
                )
            category_name = replacement
            applied_corrections.add(source_annotation_id)

        image = source_by_id[image_id]
        bbox, rotation = validated_bbox(
            annotation, int(image["width"]), int(image["height"])
        )
        record = retained_by_image_id[image_id]
        boxes_by_asset[record["asset_id"]].append(
            ImportedManualBox(
                category_name=category_name,
                bbox=bbox,
                source_annotation_id=source_annotation_id,
                source_rotation_degrees=rotation,
            )
        )
        class_counts[category_name] += 1
        role_boxes[record["dataset_role"]] += 1

    empty_assets = sorted(
        record["asset_id"]
        for record in retained_by_image_id.values()
        if not boxes_by_asset[record["asset_id"]]
    )
    if empty_assets:
        raise ValueError(
            "Retained manual images have no annotations: " + ", ".join(empty_assets)
        )

    missing_corrections = sorted(set(corrections) - applied_corrections)
    if missing_corrections:
        raise ValueError(
            "Manual corrections reference unknown annotations: "
            + ", ".join(map(str, missing_corrections))
        )

    return ManualImportResult(
        annotation_set_id=annotation_set_id,
        archive_path=metadata["archive_path"],
        archive_sha256=metadata["archive_sha256"],
        annotation_sha256=metadata["annotation_sha256"],
        source_images=len(source_images),
        retained_images=len(retained_by_image_id),
        excluded_images=len(source_images) - len(retained_by_image_id),
        retained_boxes=sum(class_counts.values()),
        excluded_boxes=excluded_boxes,
        removed_duplicate_boxes=sum(
            row["action"] == "remove_duplicate" for row in corrections.values()
        ),
        relabeled_boxes=sum(row["action"] == "relabel" for row in corrections.values()),
        classes=dict(sorted(class_counts.items())),
        roles={
            role: {"images": role_images[role], "boxes": role_boxes[role]}
            for role in sorted(role_images)
        },
        boxes_by_asset=dict(boxes_by_asset),
    )


def write_import_report(path: Path, result: ManualImportResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.report_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
