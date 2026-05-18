import cv2
from pathlib import Path


def save_detection_output(result, output_path):
    """
    Saves the YOLO detection result as an image with bounding boxes.
    """

    output_path = Path(output_path)

    # Create the output folder if it does not exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # YOLO's plot() function draws bounding boxes on the image
    annotated_image = result.plot()

    # Save the annotated image
    cv2.imwrite(str(output_path), annotated_image)

    print(f"Output image saved to: {output_path}")

    return output_path