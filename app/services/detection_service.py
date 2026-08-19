from pathlib import Path
from threading import Lock
from typing import Any

from ultralytics import YOLO

from app.config import BASE_DIR
from app.model_profile import (
    RuntimeModelProfile,
    verify_runtime_checkpoint,
)


class ObjectDetector:
    def __init__(self, model_path, *, model_factory=None):
        model_factory = model_factory or YOLO
        self._model = model_factory(str(model_path))
        self._inference_lock = Lock()

    @classmethod
    def from_runtime_profile(
        cls,
        profile: RuntimeModelProfile,
        *,
        repository_root: Path = BASE_DIR,
        model_factory=None,
    ):
        checkpoint_path = verify_runtime_checkpoint(profile, repository_root)
        return cls(checkpoint_path, model_factory=model_factory)

    def detect(
        self,
        image,
        *,
        confidence_threshold,
        image_size,
        device=None,
        max_detections=None,
        half_precision=False,
        verbose=None,
    ):
        options = {
            "conf": confidence_threshold,
            "imgsz": image_size,
        }
        if device is not None:
            options["device"] = device
        if max_detections is not None:
            options["max_det"] = max_detections
        if half_precision:
            options["half"] = True
        if verbose is not None:
            options["verbose"] = verbose
        with self._inference_lock:
            return self._model(image, **options)


def detect_objects(
    image,
    profile: RuntimeModelProfile,
):
    detector = ObjectDetector.from_runtime_profile(profile)
    return detect_objects_with_profile(image, detector, profile)


def detect_objects_with_profile(
    image,
    detector: ObjectDetector,
    profile: RuntimeModelProfile,
):
    return detector.detect(
        image,
        confidence_threshold=profile.confidence,
        image_size=profile.image_size,
        device=profile.device,
        max_detections=profile.max_detections,
        half_precision=profile.half_precision,
    )


def count_detected_objects(
    result,
    class_mapping: dict[str, str] | None = None,
):
    object_counts = {}

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = _project_class_name(result.names[class_id], class_mapping)
        if class_name is None:
            continue

        object_counts[class_name] = object_counts.get(class_name, 0) + 1

    return object_counts


def extract_detection_records(
    result,
    class_mapping: dict[str, str] | None = None,
):
    detection_records = []

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = _project_class_name(result.names[class_id], class_mapping)
        if class_name is None:
            continue
        confidence = float(box.conf[0])
        x_min, y_min, x_max, y_max = [float(value) for value in box.xyxy[0]]

        detection_records.append(
            {
                "object_class": class_name,
                "confidence": confidence,
                "bbox_x_min": x_min,
                "bbox_y_min": y_min,
                "bbox_x_max": x_max,
                "bbox_y_max": y_max,
            }
        )

    return detection_records


def _project_class_name(
    source_class: Any,
    class_mapping: dict[str, str] | None,
) -> str | None:
    source_class = str(source_class)
    if class_mapping is None:
        return source_class
    return class_mapping.get(source_class)


def build_object_count_summary_records(object_counts):
    return [
        {
            "object_class": object_class,
            "object_count": count,
        }
        for object_class, count in sorted(object_counts.items())
    ]


def print_object_summary(object_counts):
    print("\nObject Summary")
    print("--------------")

    if not object_counts:
        print("No objects detected.")
        return

    total_objects = 0

    for class_name, count in object_counts.items():
        print(f"{class_name}: {count}")
        total_objects += count

    print(f"Total objects: {total_objects}")
