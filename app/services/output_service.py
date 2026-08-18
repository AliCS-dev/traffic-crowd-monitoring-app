from pathlib import Path

import cv2


def save_detection_output(result, output_path):
    """Save a YOLO detection result as an annotated image."""

    output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    annotated_image = result.plot()

    if not cv2.imwrite(str(output_path), annotated_image):
        raise OSError(f"Detection output could not be written: {output_path}")

    print(f"Output image saved to: {output_path}")

    return output_path
