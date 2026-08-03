from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from evaluation.annotation_conversion import PROJECT_CATEGORIES
from evaluation.dataset_validation import read_csv

CATEGORY_NAMES = {category["id"]: category["name"] for category in PROJECT_CATEGORIES}
CATEGORY_COLOURS = {
    1: (40, 190, 40),
    2: (230, 180, 40),
    3: (30, 140, 255),
    4: (230, 80, 40),
    5: (180, 60, 200),
    6: (40, 200, 220),
}


def resize_for_preview(image: np.ndarray, max_width: int) -> np.ndarray:
    height, width = image.shape[:2]
    if width <= max_width:
        return image
    scale = max_width / width
    return cv2.resize(
        image,
        (max_width, round(height * scale)),
        interpolation=cv2.INTER_AREA,
    )


def draw_boxes(image: np.ndarray, annotations: list[dict[str, Any]]) -> np.ndarray:
    output = image.copy()
    thickness = max(1, round(output.shape[1] / 900))

    for annotation in annotations:
        x, y, width, height = annotation["bbox"]
        category_id = annotation["category_id"]
        colour = CATEGORY_COLOURS[category_id]
        top_left = (round(x), round(y))
        bottom_right = (round(x + width), round(y + height))
        cv2.rectangle(output, top_left, bottom_right, colour, thickness)
    return draw_legend(
        output, {annotation["category_id"] for annotation in annotations}
    )


def draw_legend(image: np.ndarray, category_ids: set[int]) -> np.ndarray:
    if not category_ids:
        return image

    output = image.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.45, output.shape[1] / 3000)
    thickness = max(1, round(output.shape[1] / 1400))
    row_height = max(24, round(output.shape[1] / 65))
    text_width = max(
        cv2.getTextSize(CATEGORY_NAMES[category_id], font, font_scale, thickness)[0][0]
        for category_id in category_ids
    )
    panel_width = text_width + row_height + 22
    panel_height = row_height * len(category_ids) + 10
    overlay = output.copy()
    cv2.rectangle(
        overlay, (8, 8), (8 + panel_width, 8 + panel_height), (20, 20, 20), -1
    )
    cv2.addWeighted(overlay, 0.78, output, 0.22, 0, output)

    for row, category_id in enumerate(sorted(category_ids)):
        y = 13 + row * row_height
        swatch_size = max(10, row_height - 10)
        cv2.rectangle(
            output,
            (14, y + 2),
            (14 + swatch_size, y + 2 + swatch_size),
            CATEGORY_COLOURS[category_id],
            -1,
        )
        cv2.putText(
            output,
            CATEGORY_NAMES[category_id],
            (22 + swatch_size, y + swatch_size),
            font,
            font_scale,
            (245, 245, 245),
            thickness,
            cv2.LINE_AA,
        )
    return output


def box_iou(first: list[float], second: list[float]) -> float:
    first_x, first_y, first_width, first_height = first
    second_x, second_y, second_width, second_height = second
    intersection_width = max(
        0.0,
        min(first_x + first_width, second_x + second_width) - max(first_x, second_x),
    )
    intersection_height = max(
        0.0,
        min(first_y + first_height, second_y + second_height) - max(first_y, second_y),
    )
    intersection = intersection_width * intersection_height
    union = first_width * first_height + second_width * second_height - intersection
    return intersection / union if union > 0 else 0.0


def duplicate_box_pairs(
    annotations: list[dict[str, Any]], threshold: float = 0.8
) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    pairs = []
    for index, first in enumerate(annotations):
        for second in annotations[index + 1 :]:
            iou = box_iou(first["bbox"], second["bbox"])
            if first["category_id"] == second["category_id"] and iou >= threshold:
                pairs.append((first, second, iou))
    return pairs


def class_conflict_box_pairs(
    annotations: list[dict[str, Any]], threshold: float = 0.8
) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    pairs = []
    for index, first in enumerate(annotations):
        for second in annotations[index + 1 :]:
            iou = box_iou(first["bbox"], second["bbox"])
            if first["category_id"] != second["category_id"] and iou >= threshold:
                pairs.append((first, second, iou))
    return pairs


def box_quality_flags(
    annotations: list[dict[str, Any]], width: int, height: int
) -> dict[str, int]:
    edge_boxes = 0
    very_small_boxes = 0
    unusually_large_boxes = 0
    for annotation in annotations:
        x, y, box_width, box_height = annotation["bbox"]
        if (
            x <= 1e-6
            or y <= 1e-6
            or x + box_width >= width - 1e-6
            or y + box_height >= height - 1e-6
        ):
            edge_boxes += 1
        if box_width < 4 or box_height < 4:
            very_small_boxes += 1
        if box_width * box_height > width * height * 0.1:
            unusually_large_boxes += 1

    return {
        "duplicate_pairs": len(duplicate_box_pairs(annotations)),
        "class_conflict_pairs": len(class_conflict_box_pairs(annotations)),
        "edge_boxes": edge_boxes,
        "very_small_boxes": very_small_boxes,
        "unusually_large_boxes": unusually_large_boxes,
    }


def source_annotation_id(annotation: dict[str, Any]) -> str:
    source_attributes = annotation.get("source_attributes", {})
    return str(source_attributes.get("source_annotation_id", ""))


def write_duplicate_preview(
    image: np.ndarray,
    first: dict[str, Any],
    second: dict[str, Any],
    output_path: Path,
) -> None:
    boxes = [first["bbox"], second["bbox"]]
    x_min = min(box[0] for box in boxes)
    y_min = min(box[1] for box in boxes)
    x_max = max(box[0] + box[2] for box in boxes)
    y_max = max(box[1] + box[3] for box in boxes)
    margin = max(60, round(max(x_max - x_min, y_max - y_min) * 2.5))
    crop_x_min = max(0, round(x_min - margin))
    crop_y_min = max(0, round(y_min - margin))
    crop_x_max = min(image.shape[1], round(x_max + margin))
    crop_y_max = min(image.shape[0], round(y_max + margin))
    crop = image[crop_y_min:crop_y_max, crop_x_min:crop_x_max].copy()

    scale = min(4.0, max(1.0, 720 / max(crop.shape[1], 1)))
    if scale > 1:
        crop = cv2.resize(
            crop,
            (round(crop.shape[1] * scale), round(crop.shape[0] * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

    colours = [(255, 220, 30), (220, 30, 220)]
    labels = ["A", "B"]
    for annotation, colour, label in zip((first, second), colours, labels, strict=True):
        x, y, width, height = annotation["bbox"]
        top_left = (
            round((x - crop_x_min) * scale),
            round((y - crop_y_min) * scale),
        )
        bottom_right = (
            round((x + width - crop_x_min) * scale),
            round((y + height - crop_y_min) * scale),
        )
        cv2.rectangle(crop, top_left, bottom_right, colour, 3)
        cv2.putText(
            crop,
            label,
            (top_left[0], max(18, top_left[1] - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            colour,
            2,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 92]):
        raise ValueError(f"Cannot write duplicate candidate preview: {output_path}")


def apply_exif_orientation(mask: np.ndarray, orientation: int) -> np.ndarray:
    transforms = {
        1: lambda value: value,
        2: lambda value: cv2.flip(value, 1),
        3: lambda value: cv2.rotate(value, cv2.ROTATE_180),
        4: lambda value: cv2.flip(value, 0),
        5: cv2.transpose,
        6: lambda value: cv2.rotate(value, cv2.ROTATE_90_CLOCKWISE),
        7: lambda value: cv2.flip(cv2.transpose(value), -1),
        8: lambda value: cv2.rotate(value, cv2.ROTATE_90_COUNTERCLOCKWISE),
    }
    try:
        return transforms[orientation](mask)
    except KeyError as error:
        raise ValueError(f"Unsupported EXIF orientation: {orientation}") from error


def orient_mask_for_image(
    mask: np.ndarray, image_path: Path, image_shape: tuple[int, int]
) -> np.ndarray:
    with Image.open(image_path) as source_image:
        orientation = int(source_image.getexif().get(274, 1))
    oriented_mask = apply_exif_orientation(mask, orientation)
    if oriented_mask.shape[:2] != image_shape:
        raise ValueError("DLR image and point mask dimensions do not match")
    return oriented_mask


def draw_point_mask(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if image.shape[:2] != mask.shape[:2]:
        raise ValueError("DLR image and point mask dimensions do not match")
    point_area = cv2.dilate(
        (mask > 0).astype(np.uint8), np.ones((7, 7), dtype=np.uint8)
    ).astype(bool)
    output = image.copy()
    overlay = np.zeros_like(output)
    overlay[point_area] = (30, 30, 255)
    output[point_area] = cv2.addWeighted(
        output[point_area], 0.25, overlay[point_area], 0.75, 0
    )
    return output


def mark_manual_annotation(image: np.ndarray) -> np.ndarray:
    output = image.copy()
    label = "MANUAL ANNOTATION REQUIRED"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.6, output.shape[1] / 1800)
    thickness = max(2, round(output.shape[1] / 900))
    (text_width, text_height), baseline = cv2.getTextSize(
        label, font, font_scale, thickness
    )
    cv2.rectangle(
        output,
        (0, 0),
        (text_width + 24, text_height + baseline + 20),
        (20, 20, 180),
        -1,
    )
    cv2.putText(
        output,
        label,
        (12, text_height + 10),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )
    return output


def remove_stale_previews(output_root: Path, expected_paths: set[Path]) -> None:
    for path in output_root.rglob("*.jpg"):
        if path not in expected_paths:
            path.unlink()


def load_coco_annotations(
    repository_root: Path, records: list[dict[str, str]]
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    annotations_by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    annotated_assets: set[str] = set()
    paths = {
        record["canonical_annotation_path"]
        for record in records
        if record["annotation_type"] == "bounding_box"
        and record["canonical_annotation_path"]
    }
    for relative_path in sorted(paths):
        data = json.loads((repository_root / relative_path).read_text(encoding="utf-8"))
        assets_by_image = {image["id"]: image["asset_id"] for image in data["images"]}
        annotated_assets.update(assets_by_image.values())
        for annotation in data["annotations"]:
            annotations_by_asset[assets_by_image[annotation["image_id"]]].append(
                annotation
            )
    return annotations_by_asset, annotated_assets


def render_previews(
    repository_root: Path, max_width: int = 1600
) -> list[dict[str, Any]]:
    _, records = read_csv(repository_root / "data/evaluation/manifest.csv")
    annotations_by_asset, annotated_assets = load_coco_annotations(
        repository_root, records
    )
    output_root = repository_root / "data/evaluation/derived/previews"
    index_rows: list[dict[str, Any]] = []
    expected_paths: set[Path] = set()
    duplicate_rows: list[dict[str, Any]] = []
    expected_duplicate_paths: set[Path] = set()

    for record in records:
        image_path = repository_root / record["evaluation_image_path"]
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Cannot read image for preview: {record['asset_id']}")

        annotations = annotations_by_asset.get(record["asset_id"], [])
        duplicate_pairs = duplicate_box_pairs(annotations)
        conflict_pairs = class_conflict_box_pairs(annotations)
        if record["annotation_type"] == "point_count":
            mask = cv2.imread(
                str(repository_root / record["annotation_source_path"]),
                cv2.IMREAD_GRAYSCALE,
            )
            if mask is None:
                raise ValueError(f"Cannot read point mask: {record['asset_id']}")
            mask = orient_mask_for_image(mask, image_path, image.shape[:2])
            preview = draw_point_mask(image, mask)
            status = "point_count"
            annotation_count = int(np.count_nonzero(mask))
        elif record["asset_id"] not in annotated_assets:
            preview = mark_manual_annotation(image)
            status = "manual_required"
            annotation_count = 0
        else:
            preview = draw_boxes(image, annotations)
            status = (
                "reviewed_manual"
                if not record["annotation_source_path"]
                else "converted_boxes"
            )
            annotation_count = len(annotations)

        quality_flags = (
            box_quality_flags(annotations, int(record["width"]), int(record["height"]))
            if record["annotation_type"] == "bounding_box"
            else {
                "duplicate_pairs": 0,
                "class_conflict_pairs": 0,
                "edge_boxes": 0,
                "very_small_boxes": 0,
                "unusually_large_boxes": 0,
            }
        )
        warning_count = sum(quality_flags.values())

        preview = resize_for_preview(preview, max_width)
        output_path = output_root / record["dataset_role"] / f"{record['asset_id']}.jpg"
        expected_paths.add(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), preview, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise ValueError(f"Cannot write preview: {output_path}")

        index_rows.append(
            {
                "asset_id": record["asset_id"],
                "dataset_role": record["dataset_role"],
                "collection_id": record["collection_id"],
                "preview_status": status,
                "review_priority": (
                    "manual_first_pass"
                    if status == "reviewed_manual"
                    else "warning"
                    if warning_count
                    else "standard"
                ),
                "annotation_count": annotation_count,
                **quality_flags,
                "preview_path": output_path.relative_to(repository_root).as_posix(),
            }
        )

        review_pairs = [("same_class_duplicate", *pair) for pair in duplicate_pairs] + [
            ("class_conflict", *pair) for pair in conflict_pairs
        ]
        for candidate_type, first, second, iou in review_pairs:
            candidate_name = f"{record['asset_id']}_{first['id']}_{second['id']}.jpg"
            candidate_path = output_root / "duplicate_candidates" / candidate_name
            expected_duplicate_paths.add(candidate_path)
            write_duplicate_preview(image, first, second, candidate_path)
            duplicate_rows.append(
                {
                    "asset_id": record["asset_id"],
                    "dataset_role": record["dataset_role"],
                    "candidate_type": candidate_type,
                    "category_a": CATEGORY_NAMES[first["category_id"]],
                    "category_b": CATEGORY_NAMES[second["category_id"]],
                    "canonical_annotation_a": first["id"],
                    "canonical_annotation_b": second["id"],
                    "source_annotation_a": source_annotation_id(first),
                    "source_annotation_b": source_annotation_id(second),
                    "iou": f"{iou:.4f}",
                    "bbox_a": json.dumps(first["bbox"], separators=(",", ":")),
                    "bbox_b": json.dumps(second["bbox"], separators=(",", ":")),
                    "preview_path": candidate_path.relative_to(
                        repository_root
                    ).as_posix(),
                }
            )

    remove_stale_previews(output_root, expected_paths | expected_duplicate_paths)
    priority_order = {"manual_first_pass": 0, "warning": 1, "standard": 2}
    index_rows.sort(
        key=lambda row: (
            priority_order[row["review_priority"]],
            -sum(
                row[field]
                for field in (
                    "duplicate_pairs",
                    "class_conflict_pairs",
                    "edge_boxes",
                    "very_small_boxes",
                    "unusually_large_boxes",
                )
            ),
            row["asset_id"],
        )
    )
    index_path = output_root / "preview_index.csv"
    with index_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "asset_id",
                "dataset_role",
                "collection_id",
                "preview_status",
                "review_priority",
                "annotation_count",
                "duplicate_pairs",
                "class_conflict_pairs",
                "edge_boxes",
                "very_small_boxes",
                "unusually_large_boxes",
                "preview_path",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(index_rows)

    duplicate_index_path = output_root / "duplicate_candidates.csv"
    with duplicate_index_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "asset_id",
                "dataset_role",
                "candidate_type",
                "category_a",
                "category_b",
                "canonical_annotation_a",
                "canonical_annotation_b",
                "source_annotation_a",
                "source_annotation_b",
                "iou",
                "bbox_a",
                "bbox_b",
                "preview_path",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(duplicate_rows)
    return index_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render visual previews of evaluation annotations."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--max-width", type=int, default=1600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = render_previews(args.repository_root.resolve(), max_width=args.max_width)
    status_counts = Counter(row["preview_status"] for row in rows)
    print(f"Rendered {len(rows)} annotation previews")
    print(
        "Statuses: "
        + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items()))
    )


if __name__ == "__main__":
    main()
