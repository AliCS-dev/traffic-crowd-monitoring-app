from pathlib import Path

import cv2


def save_image_output(image, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not cv2.imwrite(str(output_path), image):
        raise OSError(f"Image output could not be written: {output_path}")

    return output_path


def save_detection_output(
    result,
    output_path,
    *,
    expected_width=None,
    expected_height=None,
):
    """Save a YOLO detection result as an annotated image."""
    annotated_image = result.plot()
    if expected_width is not None or expected_height is not None:
        if expected_width is None or expected_height is None:
            raise ValueError(
                "Expected image width and height must be provided together."
            )
        if annotated_image.shape[:2] != (expected_height, expected_width):
            raise ValueError(
                "Annotated image dimensions do not match processed dimensions."
            )
    return save_image_output(annotated_image, output_path)
