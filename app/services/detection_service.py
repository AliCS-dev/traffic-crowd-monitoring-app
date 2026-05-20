from ultralytics import YOLO


def detect_objects(image, model_path, confidence_threshold=0.15, image_size=1280):
    model = YOLO(str(model_path))

    results = model(
        image,
        conf=confidence_threshold,
        imgsz=image_size
    )

    return results


def count_detected_objects(result):
    object_counts = {}

    for box in result.boxes:
        class_id = int(box.cls[0])
        class_name = result.names[class_id]

        object_counts[class_name] = object_counts.get(class_name, 0) + 1

    return object_counts


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
