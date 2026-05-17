from ultralytics import YOLO
from collections import Counter
from pathlib import Path

# Paths
image_path = Path("data/input/sample_image.jpg")
output_path = Path("data/output/sample_detected.jpg")



model = YOLO("yolo26n.pt")

# Run detection
results = model(image_path, conf=0.1, imgsz=2016)

for result in results:
    # Save image with bounding boxes
    result.save(filename=str(output_path))

    # Get class names and confidence scores
    names = [result.names[cls.item()] for cls in result.boxes.cls.int()]
    confs = result.boxes.conf

    # Count detected object types
    counts = Counter(names)

    print("Detection completed.")
    print(f"Input image: {image_path}")
    print(f"Output image saved to: {output_path}")

    print("\nDetected object counts:")
    for object_name, count in counts.items():
        print(f"{object_name}: {count}")

    print("\nConfidence scores:")
    for name, conf in zip(names, confs):
        print(f"{name}: {conf:.2f}")