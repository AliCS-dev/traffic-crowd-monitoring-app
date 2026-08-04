from ultralytics import YOLO


class ObjectDetector:
    def __init__(self, model_path):
        self._model = YOLO(str(model_path))

    def detect(
        self,
        image,
        confidence_threshold=0.15,
        image_size=1280,
        *,
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
        return self._model(image, **options)


def detect_objects(image, model_path, confidence_threshold=0.15, image_size=1280):
    detector = ObjectDetector(model_path)
    return detector.detect(
        image,
        confidence_threshold=confidence_threshold,
        image_size=image_size,
    )


def count_detected_objects(result):
    object_counts = {}

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = result.names[class_id]

        object_counts[class_name] = object_counts.get(class_name, 0) + 1

    return object_counts


def extract_detection_records(result):
    detection_records = []

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = result.names[class_id]
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
