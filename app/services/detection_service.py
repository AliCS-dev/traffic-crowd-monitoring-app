from ultralytics import YOLO


def detect_objects(image, model_path, confidence_threshold=0.15, image_size=1280):
    model = YOLO(str(model_path))

    results = model(image, conf=confidence_threshold, imgsz=image_size)

    return results


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
