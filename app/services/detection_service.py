from ultralytics import YOLO


def detect_objects(image, model_path):
    model = YOLO(str(model_path))
    results = model(image)

    return results