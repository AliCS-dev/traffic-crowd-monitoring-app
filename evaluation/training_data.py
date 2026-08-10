import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from evaluation.annotation_conversion import parse_okutama_file
from evaluation.training_config import FineTuningConfig


class TrainingDataError(RuntimeError):
    """Raised when fine-tuning data cannot be prepared safely."""


@dataclass(frozen=True)
class PreparedDataset:
    dataset_yaml: Path
    summary_path: Path
    training_images: int
    validation_images: int
    training_boxes: int
    validation_boxes: int
    training_source_groups: tuple[str, ...]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def _reset_output_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    for split in ("train", "val"):
        (path / "images" / split).mkdir(parents=True, exist_ok=True)
        (path / "labels" / split).mkdir(parents=True, exist_ok=True)


def _link(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise TrainingDataError(f"Image is missing: {source}")
    destination.symlink_to(source.resolve())


def _yolo_line(class_id: int, bbox: tuple[float, float, float, float]) -> str:
    x_min, y_min, width, height = bbox
    center_x = (x_min + width / 2) / 1280
    center_y = (y_min + height / 2) / 720
    return (
        f"{class_id} {center_x:.8f} {center_y:.8f} "
        f"{width / 1280:.8f} {height / 720:.8f}"
    )


def _write_training_split(
    repository_root: Path,
    output_directory: Path,
    rows: list[dict[str, str]],
    frame_stride: int,
    person_class_id: int,
) -> tuple[int, int, tuple[str, ...]]:
    image_count = 0
    box_count = 0
    source_groups = set()
    for row in sorted(rows, key=lambda item: item["selection_id"]):
        source_groups.add(row["source_group_id"])
        image_directory = repository_root / row["source_path"]
        frame_paths = sorted(
            image_directory.glob("*.jpg"), key=lambda path: int(path.stem)
        )
        if not frame_paths:
            raise TrainingDataError(
                f"No training images found for {row['selection_id']}: {image_directory}"
            )
        selected_paths = frame_paths[::frame_stride]
        selected_frames = {int(path.stem) for path in selected_paths}
        boxes_by_frame = parse_okutama_file(
            repository_root / row["annotation_source"],
            selected_frames,
            width=1280,
            height=720,
        )
        for image_path in selected_paths:
            frame = int(image_path.stem)
            stem = f"{row['selection_id']}-f{frame:06d}"
            _link(image_path, output_directory / "images/train" / f"{stem}.jpg")
            boxes = boxes_by_frame[frame]
            label_lines = [_yolo_line(person_class_id, box.bbox) for box in boxes]
            (output_directory / "labels/train" / f"{stem}.txt").write_text(
                "\n".join(label_lines) + ("\n" if label_lines else ""),
                encoding="utf-8",
            )
            image_count += 1
            box_count += len(boxes)
    return image_count, box_count, tuple(sorted(source_groups))


def _write_validation_split(
    repository_root: Path,
    output_directory: Path,
    annotations_path: Path,
    class_ids: dict[str, int],
    forbidden_source_groups: set[str],
) -> tuple[int, int]:
    data = json.loads(annotations_path.read_text(encoding="utf-8"))
    categories = {item["id"]: item["name"] for item in data["categories"]}
    annotations_by_image: dict[int, list[dict[str, Any]]] = {}
    for annotation in data["annotations"]:
        category_name = categories[annotation["category_id"]]
        if category_name not in class_ids:
            raise TrainingDataError(
                f"Validation class has no training mapping: {category_name}"
            )
        annotations_by_image.setdefault(annotation["image_id"], []).append(annotation)

    image_count = 0
    box_count = 0
    for image in sorted(data["images"], key=lambda item: item["asset_id"]):
        source_group = image["source_group_id"]
        if source_group in forbidden_source_groups:
            raise TrainingDataError(
                f"Source-group leakage between training and validation: {source_group}"
            )
        annotations = annotations_by_image.get(image["id"], [])
        extension = Path(image["file_name"]).suffix.lower() or ".jpg"
        destination_name = f"{image['asset_id']}{extension}"
        _link(
            repository_root / image["file_name"],
            output_directory / "images/val" / destination_name,
        )
        label_lines = []
        for annotation in annotations:
            category_name = categories[annotation["category_id"]]
            x_min, y_min, width, height = map(float, annotation["bbox"])
            image_width = float(image["width"])
            image_height = float(image["height"])
            label_lines.append(
                f"{class_ids[category_name]} "
                f"{(x_min + width / 2) / image_width:.8f} "
                f"{(y_min + height / 2) / image_height:.8f} "
                f"{width / image_width:.8f} {height / image_height:.8f}"
            )
        label_path = (
            output_directory / "labels/val" / Path(destination_name).with_suffix(".txt")
        )
        label_path.write_text(
            "\n".join(label_lines) + ("\n" if label_lines else ""),
            encoding="utf-8",
        )
        image_count += 1
        box_count += len(label_lines)
    return image_count, box_count


def prepare_training_dataset(
    repository_root: Path, config: FineTuningConfig
) -> PreparedDataset:
    selection_path = repository_root / config.dataset.selection_plan_path
    rows = _read_csv(selection_path)
    source_roles: dict[str, set[str]] = {}
    for row in rows:
        source_roles.setdefault(row["source_group_id"], set()).add(row["dataset_role"])
    overlaps = sorted(group for group, roles in source_roles.items() if len(roles) > 1)
    if overlaps:
        raise TrainingDataError(
            "Source groups have multiple dataset roles: " + ", ".join(overlaps)
        )

    training_rows = [
        row
        for row in rows
        if row["collection_id"] == config.dataset.collection_id
        and row["dataset_role"] == config.dataset.role
    ]
    if not training_rows:
        raise TrainingDataError("No rows match the configured training collection")
    if any(row["annotation_type"] != "bounding_box" for row in training_rows):
        raise TrainingDataError("Training rows must use bounding-box annotations")

    output_directory = repository_root / config.dataset.output_directory
    _reset_output_directory(output_directory)
    mapped_ids = config.mapped_class_ids()
    try:
        person_class_id = mapped_ids["person"]
    except KeyError as error:
        raise TrainingDataError("project_class_mapping must include person") from error

    train_images, train_boxes, source_groups = _write_training_split(
        repository_root,
        output_directory,
        training_rows,
        config.dataset.frame_stride,
        person_class_id,
    )
    validation_images, validation_boxes = _write_validation_split(
        repository_root,
        output_directory,
        repository_root / config.dataset.validation_annotations_path,
        mapped_ids,
        set(source_groups),
    )

    dataset_yaml = output_directory / "dataset.yaml"
    dataset_yaml.write_text(
        yaml.safe_dump(
            {
                "path": str(output_directory.resolve()),
                "train": "images/train",
                "val": "images/val",
                "names": dict(enumerate(config.source_classes)),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    summary_path = output_directory / "dataset_summary.json"
    summary = {
        "config_sha256": config.config_sha256,
        "selection_plan": config.dataset.selection_plan_path.as_posix(),
        "selection_plan_role": config.dataset.role,
        "collection_id": config.dataset.collection_id,
        "frame_stride": config.dataset.frame_stride,
        "training_images": train_images,
        "training_boxes": train_boxes,
        "training_source_groups": list(source_groups),
        "validation_images": validation_images,
        "validation_boxes": validation_boxes,
        "training_class_counts": {"person": train_boxes},
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return PreparedDataset(
        dataset_yaml=dataset_yaml,
        summary_path=summary_path,
        training_images=train_images,
        validation_images=validation_images,
        training_boxes=train_boxes,
        validation_boxes=validation_boxes,
        training_source_groups=source_groups,
    )
