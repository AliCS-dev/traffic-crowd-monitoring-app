from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2

from evaluation.annotation_conversion import (
    PROJECT_CATEGORIES,
    clip_xyxy,
)
from evaluation.annotation_preview import draw_boxes, resize_for_preview
from evaluation.dataset_selection import sha256
from evaluation.dataset_validation import read_csv

MODEL_CLASS_MAP = {
    "bicycle": 2,
    "motorcycle": 3,
    "car": 4,
    "bus": 5,
    "truck": 6,
}


def manual_records(manifest_path: Path) -> list[dict[str, str]]:
    _, records = read_csv(manifest_path)
    selected = [
        record
        for record in records
        if record["annotation_type"] == "bounding_box"
        and not record["annotation_source_path"]
    ]
    return sorted(selected, key=lambda record: record["asset_id"])


def task_filename(record: dict[str, str]) -> str:
    suffix = Path(record["evaluation_image_path"]).suffix.lower()
    return f"{record['asset_id']}{suffix}"


def coco_images(
    records: list[dict[str, str]], repository_root: Path, image_directory: Path
) -> list[dict[str, Any]]:
    images = []
    image_directory.mkdir(parents=True, exist_ok=True)
    for image_id, record in enumerate(records, start=1):
        filename = task_filename(record)
        source = repository_root / record["evaluation_image_path"]
        destination = image_directory / filename
        shutil.copy2(source, destination)
        images.append(
            {
                "id": image_id,
                "file_name": filename,
                "width": int(record["width"]),
                "height": int(record["height"]),
                "asset_id": record["asset_id"],
                "dataset_role": record["dataset_role"],
                "source_group_id": record["source_group_id"],
                "source_url": record["source_url"],
                "license_id": record["license_id"],
                "creator": record["creator"],
                "sha256": record["image_sha256"],
            }
        )
    return images


def draft_annotations(
    records: list[dict[str, str]],
    images: list[dict[str, Any]],
    repository_root: Path,
    model_path: Path,
    confidence: float,
    image_size: int,
) -> list[dict[str, Any]]:
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    image_ids = {image["asset_id"]: image["id"] for image in images}
    annotations: list[dict[str, Any]] = []

    for record in records:
        result = model.predict(
            source=str(repository_root / record["evaluation_image_path"]),
            conf=confidence,
            imgsz=image_size,
            max_det=300,
            verbose=False,
        )[0]
        for box in result.boxes:
            source_class_id = int(box.cls[0])
            source_class_name = result.names[source_class_id]
            category_id = MODEL_CLASS_MAP.get(source_class_name)
            if category_id is None:
                continue

            x_min, y_min, x_max, y_max = [float(value) for value in box.xyxy[0]]
            x, y, width, height = clip_xyxy(
                x_min,
                y_min,
                x_max,
                y_max,
                int(record["width"]),
                int(record["height"]),
            )
            annotations.append(
                {
                    "id": len(annotations) + 1,
                    "image_id": image_ids[record["asset_id"]],
                    "category_id": category_id,
                    "bbox": [
                        round(x, 6),
                        round(y, 6),
                        round(width, 6),
                        round(height, 6),
                    ],
                    "area": round(width * height, 6),
                    "iscrowd": 0,
                    "segmentation": [],
                    "source_attributes": {
                        "annotation_status": "model_assisted_draft",
                        "model_class": source_class_name,
                        "confidence": round(float(box.conf[0]), 6),
                    },
                }
            )
    return annotations


def write_task_assets(
    path: Path, records: list[dict[str, str]], images: list[dict[str, Any]]
) -> None:
    image_names = {image["asset_id"]: image["file_name"] for image in images}
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "asset_id",
                "task_filename",
                "dataset_role",
                "source_group_id",
                "source_url",
                "creator",
                "license_id",
                "image_sha256",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "asset_id": record["asset_id"],
                    "task_filename": image_names[record["asset_id"]],
                    "dataset_role": record["dataset_role"],
                    "source_group_id": record["source_group_id"],
                    "source_url": record["source_url"],
                    "creator": record["creator"],
                    "license_id": record["license_id"],
                    "image_sha256": record["image_sha256"],
                }
            )


def create_task_archive(task_root: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path in sorted(task_root.rglob("*")):
            if path.is_file():
                archive_path_name = path.relative_to(task_root).as_posix()
                archive_info = zipfile.ZipInfo(
                    archive_path_name, date_time=(1980, 1, 1, 0, 0, 0)
                )
                archive_info.compress_type = zipfile.ZIP_DEFLATED
                archive_info.external_attr = 0o100644 << 16
                archive.writestr(archive_info, path.read_bytes())


def render_draft_previews(
    records: list[dict[str, str]],
    images: list[dict[str, Any]],
    annotations: list[dict[str, Any]],
    repository_root: Path,
    output_directory: Path,
) -> None:
    annotations_by_image: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for annotation in annotations:
        annotations_by_image[annotation["image_id"]].append(annotation)
    image_ids = {image["asset_id"]: image["id"] for image in images}

    output_directory.mkdir(parents=True, exist_ok=True)
    for record in records:
        image = cv2.imread(str(repository_root / record["evaluation_image_path"]))
        if image is None:
            raise ValueError(f"Cannot read draft image: {record['asset_id']}")
        preview = draw_boxes(image, annotations_by_image[image_ids[record["asset_id"]]])
        preview = resize_for_preview(preview, max_width=1600)
        output_path = output_directory / f"{record['asset_id']}.jpg"
        if not cv2.imwrite(str(output_path), preview, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise ValueError(f"Cannot write draft preview: {output_path}")


def prepare_manual_annotation_task(
    repository_root: Path,
    model_path: Path,
    confidence: float = 0.15,
    image_size: int = 1920,
    include_draft_boxes: bool = True,
) -> tuple[Path, dict[str, Any]]:
    records = manual_records(repository_root / "data/evaluation/manifest.csv")
    if not records:
        raise ValueError("No manual annotation records were found")

    output_root = repository_root / "data/evaluation/derived/manual_annotation"
    mode = "draft" if include_draft_boxes else "blank"
    task_name = f"wikimedia_manual_v1_{mode}"
    task_root = output_root / task_name
    image_directory = task_root / "images" / "default"
    annotation_directory = task_root / "annotations"
    annotation_directory.mkdir(parents=True, exist_ok=True)

    images = coco_images(records, repository_root, image_directory)
    annotations = (
        draft_annotations(
            records,
            images,
            repository_root,
            model_path,
            confidence,
            image_size,
        )
        if include_draft_boxes
        else []
    )
    model_hash = sha256(model_path) if include_draft_boxes else ""
    coco = {
        "info": {
            "description": "Wikimedia manual annotation task",
            "version": "1.0-draft",
            "annotation_status": "model_assisted_draft"
            if include_draft_boxes
            else "unlabelled",
            "model_sha256": model_hash,
            "confidence_threshold": confidence if include_draft_boxes else None,
            "image_size": image_size if include_draft_boxes else None,
        },
        "images": images,
        "annotations": annotations,
        "categories": PROJECT_CATEGORIES,
    }
    annotation_path = annotation_directory / "instances_default.json"
    annotation_path.write_text(
        json.dumps(coco, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_task_assets(task_root / "task_assets.csv", records, images)
    if include_draft_boxes:
        render_draft_previews(
            records,
            images,
            annotations,
            repository_root,
            output_root / "draft_previews",
        )

    readme = (
        "This package contains model-assisted draft annotations.\n"
        "They are not ground truth and must be reviewed image by image.\n"
        "Add missed objects, delete false boxes, correct classes, and tighten boxes.\n"
        "Do not change filenames or category identifiers.\n"
    )
    (task_root / "REVIEW_REQUIRED.txt").write_text(readme, encoding="utf-8")

    archive_path = output_root / f"{task_name}_cvat.zip"
    create_task_archive(task_root, archive_path)
    summary = {
        "images": len(images),
        "draft_boxes": len(annotations),
        "classes": dict(
            sorted(
                Counter(
                    next(
                        category["name"]
                        for category in PROJECT_CATEGORIES
                        if category["id"] == annotation["category_id"]
                    )
                    for annotation in annotations
                ).items()
            )
        ),
        "model_sha256": model_hash,
        "archive_sha256": sha256(archive_path),
    }
    (output_root / f"{task_name}_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return archive_path, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a CVAT task for the Wikimedia evaluation images."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "models/yolo26n.pt",
    )
    parser.add_argument("--confidence", type=float, default=0.15)
    parser.add_argument("--image-size", type=int, default=1920)
    parser.add_argument("--without-draft-boxes", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    archive_path, summary = prepare_manual_annotation_task(
        repository_root=args.repository_root.resolve(),
        model_path=args.model.resolve(),
        confidence=args.confidence,
        image_size=args.image_size,
        include_draft_boxes=not args.without_draft_boxes,
    )
    print(f"Prepared CVAT task: {archive_path}")
    print(f"Images: {summary['images']}")
    print(f"Draft boxes requiring review: {summary['draft_boxes']}")
    print(f"Draft classes: {summary['classes']}")
    print(f"Archive SHA-256: {summary['archive_sha256']}")


if __name__ == "__main__":
    main()
