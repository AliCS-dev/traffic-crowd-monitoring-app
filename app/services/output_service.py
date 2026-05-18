import cv2
from pathlib import Path


def save_detection_output(result, output_path):
    """
    Saves an image with YOLO bounding boxes drawn on it.
    """

    output_path = Path(output_path)

    annotated_image = result.plot()

    cv2.imwrite(str(output_path), annotated_image)

    print(f"Detection output saved to: {output_path}")

    return output_path