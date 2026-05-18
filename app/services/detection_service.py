from ultralytics import YOLO


def detect_objects(image, model_path, confidence_threshold=0.15, image_size=1280):
   

    model = YOLO(str(model_path))

    results = model(
        image,
        conf=confidence_threshold,
        imgsz=image_size
    )

    return results