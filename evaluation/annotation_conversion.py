from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from evaluation.manual_annotation_import import (
    ManualImportResult,
    import_reviewed_annotations,
    write_import_report,
)

PROJECT_CATEGORIES = [
    {"id": 1, "name": "person", "supercategory": "person"},
    {"id": 2, "name": "bicycle", "supercategory": "road_vehicle"},
    {"id": 3, "name": "motorcycle", "supercategory": "road_vehicle"},
    {"id": 4, "name": "car_or_van", "supercategory": "road_vehicle"},
    {"id": 5, "name": "bus", "supercategory": "road_vehicle"},
    {"id": 6, "name": "truck", "supercategory": "road_vehicle"},
]
TRAFFIC_CLASS_MAP = {0: 4, 1: 3}
DATASET_ROLES = ("training", "validation", "held_out_test")


@dataclass(frozen=True)
class ConvertedBox:
    category_id: int
    bbox: tuple[float, float, float, float]
    source_attributes: dict[str, Any]


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def clip_xyxy(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    values = (x_min, y_min, x_max, y_max)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Bounding-box coordinates must be finite")

    clipped_x_min = min(max(x_min, 0.0), float(width))
    clipped_y_min = min(max(y_min, 0.0), float(height))
    clipped_x_max = min(max(x_max, 0.0), float(width))
    clipped_y_max = min(max(y_max, 0.0), float(height))
    box_width = clipped_x_max - clipped_x_min
    box_height = clipped_y_max - clipped_y_min
    if box_width <= 0 or box_height <= 0:
        raise ValueError("Bounding box has no area after clipping")

    return clipped_x_min, clipped_y_min, box_width, box_height


def convert_yolo_line(line: str, width: int, height: int) -> ConvertedBox:
    fields = line.split()
    if len(fields) != 5:
        raise ValueError(f"Malformed YOLO annotation: {line!r}")

    source_class = int(fields[0])
    try:
        category_id = TRAFFIC_CLASS_MAP[source_class]
    except KeyError as error:
        raise ValueError(f"Unknown Traffic UAV class ID: {source_class}") from error

    center_x, center_y, box_width, box_height = map(float, fields[1:])
    if box_width <= 0 or box_height <= 0:
        raise ValueError(f"YOLO annotation has non-positive size: {line!r}")

    x_min = (center_x - box_width / 2) * width
    y_min = (center_y - box_height / 2) * height
    x_max = (center_x + box_width / 2) * width
    y_max = (center_y + box_height / 2) * height
    bbox = clip_xyxy(x_min, y_min, x_max, y_max, width, height)
    return ConvertedBox(
        category_id=category_id,
        bbox=bbox,
        source_attributes={"source_class_id": source_class},
    )


def parse_okutama_line(
    line: str, width: int, height: int
) -> tuple[int, ConvertedBox | None]:
    fields = shlex.split(line)
    if len(fields) < 10:
        raise ValueError(f"Malformed Okutama annotation: {line!r}")

    track_id = int(fields[0])
    source_x_min, source_y_min, source_x_max, source_y_max = map(float, fields[1:5])
    frame = int(fields[5])
    lost = int(fields[6])
    occluded = int(fields[7])
    generated = int(fields[8])
    source_label = fields[9]

    if source_label.lower() != "person":
        raise ValueError(f"Unknown Okutama label: {source_label}")
    if lost:
        return frame, None

    scale_x = width / 3840.0
    scale_y = height / 2160.0
    bbox = clip_xyxy(
        source_x_min * scale_x,
        source_y_min * scale_y,
        source_x_max * scale_x,
        source_y_max * scale_y,
        width,
        height,
    )
    return frame, ConvertedBox(
        category_id=1,
        bbox=bbox,
        source_attributes={
            "track_id": track_id,
            "occluded": bool(occluded),
            "generated": bool(generated),
        },
    )


def parse_okutama_file(
    path: Path, selected_frames: set[int], width: int, height: int
) -> dict[int, list[ConvertedBox]]:
    boxes_by_frame: dict[int, list[ConvertedBox]] = {
        frame: [] for frame in selected_frames
    }
    with path.open(encoding="utf-8") as annotation_file:
        for line_number, raw_line in enumerate(annotation_file, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                frame, box = parse_okutama_line(line, width, height)
            except ValueError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
            if frame in boxes_by_frame and box is not None:
                boxes_by_frame[frame].append(box)
    return boxes_by_frame


def coco_image(record: dict[str, str], image_id: int) -> dict[str, Any]:
    return {
        "id": image_id,
        "file_name": record["evaluation_image_path"],
        "width": int(record["width"]),
        "height": int(record["height"]),
        "asset_id": record["asset_id"],
        "collection_id": record["collection_id"],
        "source_group_id": record["source_group_id"],
        "source_split": record["source_split"],
        "dataset_role": record["dataset_role"],
        "sha256": record["image_sha256"],
    }


def coco_annotation(
    box: ConvertedBox, annotation_id: int, image_id: int
) -> dict[str, Any]:
    x, y, width, height = box.bbox
    return {
        "id": annotation_id,
        "image_id": image_id,
        "category_id": box.category_id,
        "bbox": [round(x, 6), round(y, 6), round(width, 6), round(height, 6)],
        "area": round(width * height, 6),
        "iscrowd": 0,
        "segmentation": [],
        "source_attributes": box.source_attributes,
    }


def traffic_boxes(record: dict[str, str], repository_root: Path) -> list[ConvertedBox]:
    path = repository_root / record["annotation_source_path"]
    boxes = []
    with path.open(encoding="utf-8") as annotation_file:
        for line_number, raw_line in enumerate(annotation_file, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                boxes.append(
                    convert_yolo_line(line, int(record["width"]), int(record["height"]))
                )
            except ValueError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    return boxes


def convert_role_to_coco(
    records: list[dict[str, str]],
    role: str,
    repository_root: Path,
    output_path: Path,
    manual_import: ManualImportResult | None = None,
) -> tuple[int, Counter[int]]:
    manual_boxes = manual_import.boxes_by_asset if manual_import else {}
    role_records = [
        record
        for record in records
        if record["dataset_role"] == role
        and record["annotation_type"] == "bounding_box"
        and (record["annotation_source_path"] or record["asset_id"] in manual_boxes)
    ]
    role_records.sort(key=lambda record: record["asset_id"])
    images = [
        coco_image(record, image_id)
        for image_id, record in enumerate(role_records, start=1)
    ]
    image_ids = {
        record["asset_id"]: image_id
        for image_id, record in enumerate(role_records, start=1)
    }

    annotations: list[dict[str, Any]] = []
    category_counts: Counter[int] = Counter()

    for record in role_records:
        if record["collection_id"] != "traffic_uav":
            continue
        for box in traffic_boxes(record, repository_root):
            annotation_id = len(annotations) + 1
            annotations.append(
                coco_annotation(box, annotation_id, image_ids[record["asset_id"]])
            )
            category_counts[box.category_id] += 1

    okutama_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in role_records:
        if record["collection_id"] == "okutama_action":
            okutama_groups[record["annotation_source_path"]].append(record)

    for source_path, group_records in sorted(okutama_groups.items()):
        selected_frames = {int(record["frame_number"]) for record in group_records}
        first_record = group_records[0]
        boxes_by_frame = parse_okutama_file(
            repository_root / source_path,
            selected_frames,
            int(first_record["width"]),
            int(first_record["height"]),
        )
        for record in sorted(group_records, key=lambda item: item["asset_id"]):
            boxes = boxes_by_frame[int(record["frame_number"])]
            for box in boxes:
                annotation_id = len(annotations) + 1
                annotations.append(
                    coco_annotation(box, annotation_id, image_ids[record["asset_id"]])
                )
                category_counts[box.category_id] += 1

    category_ids = {category["name"]: category["id"] for category in PROJECT_CATEGORIES}
    for record in role_records:
        for imported_box in manual_boxes.get(record["asset_id"], []):
            category_id = category_ids[imported_box.category_name]
            box = ConvertedBox(
                category_id=category_id,
                bbox=imported_box.bbox,
                source_attributes={
                    "annotation_source": "manual_cvat",
                    "source_annotation_id": imported_box.source_annotation_id,
                    "source_rotation_degrees": imported_box.source_rotation_degrees,
                    "annotation_archive_sha256": manual_import.archive_sha256,
                },
            )
            annotation_id = len(annotations) + 1
            annotations.append(
                coco_annotation(box, annotation_id, image_ids[record["asset_id"]])
            )
            category_counts[category_id] += 1

    info: dict[str, Any] = {
        "description": "Aerial traffic and person evaluation annotations",
        "version": records[0]["dataset_version"] if records else "unknown",
    }
    if manual_import and any(
        record["asset_id"] in manual_boxes for record in role_records
    ):
        info["manual_annotation_set_id"] = manual_import.annotation_set_id
        info["manual_annotation_archive_sha256"] = manual_import.archive_sha256
    output = {
        "info": info,
        "images": images,
        "annotations": annotations,
        "categories": PROJECT_CATEGORIES,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return len(images), category_counts


def count_point_mask(path: Path) -> int:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError(f"Cannot read DLR annotation mask: {path}")
    values = set(int(value) for value in np.unique(mask))
    if not values.issubset({0, 255}):
        raise ValueError(f"DLR annotation mask is not binary: {path}")
    return int(np.count_nonzero(mask))


def convert_dlr_counts(
    records: list[dict[str, str]], repository_root: Path, output_path: Path
) -> list[dict[str, Any]]:
    output_rows = []
    for record in sorted(records, key=lambda item: item["asset_id"]):
        if record["annotation_type"] != "point_count":
            continue
        source_path = repository_root / record["annotation_source_path"]
        output_rows.append(
            {
                "asset_id": record["asset_id"],
                "dataset_role": record["dataset_role"],
                "source_group_id": record["source_group_id"],
                "person_count": count_point_mask(source_path),
                "annotation_source_path": record["annotation_source_path"],
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "asset_id",
                "dataset_role",
                "source_group_id",
                "person_count",
                "annotation_source_path",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output_rows)
    return output_rows


def convert_annotations(repository_root: Path) -> None:
    manifest_path = repository_root / "data/evaluation/manifest.csv"
    output_directory = repository_root / "data/evaluation/derived/annotations"
    records = read_manifest(manifest_path)
    manual_records = [
        record
        for record in records
        if record["annotation_type"] == "bounding_box"
        and not record["annotation_source_path"]
    ]
    manual_import = None
    if manual_records:
        manual_import = import_reviewed_annotations(
            repository_root=repository_root,
            records=records,
            metadata_path=repository_root
            / "data/evaluation/manual_annotation_exports.csv",
            exclusions_path=repository_root / "data/evaluation/exclusions.csv",
            corrections_path=repository_root
            / "data/evaluation/manual_annotation_corrections.csv",
            project_category_names={
                category["name"] for category in PROJECT_CATEGORIES
            },
        )
        write_import_report(
            repository_root
            / "data/evaluation/derived/reports/manual_annotation_import.json",
            manual_import,
        )
        print(
            "Manual CVAT import: "
            f"{manual_import.retained_images} retained images and "
            f"{manual_import.retained_boxes} boxes; "
            f"{manual_import.excluded_images} excluded images skipped"
        )

    for role in DATASET_ROLES:
        image_count, category_counts = convert_role_to_coco(
            records,
            role,
            repository_root,
            output_directory / f"instances_{role}.json",
            manual_import,
        )
        print(
            f"{role}: {image_count} images and "
            f"{sum(category_counts.values())} bounding boxes"
        )

    count_rows = convert_dlr_counts(
        records,
        repository_root,
        output_directory / "dlr_person_counts.csv",
    )
    print(
        f"DLR: {len(count_rows)} images and "
        f"{sum(row['person_count'] for row in count_rows)} person points"
    )

    imported_ids = set(manual_import.boxes_by_asset) if manual_import else set()
    missing_manual = sorted(
        record["asset_id"]
        for record in manual_records
        if record["asset_id"] not in imported_ids
    )
    if missing_manual:
        raise ValueError(
            "Manual bounding-box annotation still required: "
            + ", ".join(missing_manual)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert selected source annotations into evaluation formats."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    convert_annotations(args.repository_root.resolve())


if __name__ == "__main__":
    main()
