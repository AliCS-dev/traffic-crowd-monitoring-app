import cv2
from pathlib import Path


def save_detection_output(result, output_path):
    """Save a YOLO detection result as an annotated image."""

    output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    annotated_image = result.plot()

    cv2.imwrite(str(output_path), annotated_image)

    print(f"Output image saved to: {output_path}")

    return output_path
