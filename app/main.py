import argparse

from app.services.image_service import load_input_image
from app.services.preprocessing_service import preprocess_image_for_detection
from app.services.detection_service import (
    detect_objects,
    count_detected_objects,
    print_object_summary,
)
from app.services.output_service import save_detection_output
from app.config import MODEL_PATH, SAMPLE_IMAGE_PATH, SAMPLE_OUTPUT_PATH


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run object detection on an input image."
    )

    parser.add_argument(
        "--image",
        default=SAMPLE_IMAGE_PATH,
        help="Path to the input image."
    )

    parser.add_argument(
        "--output",
        default=SAMPLE_OUTPUT_PATH,
        help="Path where the annotated output image will be saved."
    )

    parser.add_argument(
        "--confidence",
        type=float,
        default=0.10,
        help="Minimum detection confidence threshold."
    )

    parser.add_argument(
        "--image-size",
        type=int,
        default=1280,
        help="YOLO inference image size."
    )

    parser.add_argument(
        "--scale-factor",
        type=int,
        default=2,
        help="Image resize scale factor before detection."
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    image = load_input_image(args.image)
    height, width = image.shape[:2]

    print("Image loaded successfully.")
    print(f"Input image: {args.image}")
    print(f"Width: {width}")
    print(f"Height: {height}")
    print("Image is ready for preprocessing.")

    processed_image = preprocess_image_for_detection(
        image,
        scale_factor=args.scale_factor
    )

    print("Image preprocessing completed.")
    print("Image is ready for object detection.")

    results = detect_objects(
        processed_image,
        MODEL_PATH,
        confidence_threshold=args.confidence,
        image_size=args.image_size
    )

    first_result = results[0]
    object_counts = count_detected_objects(first_result)

    print("Object detection completed.")
    print_object_summary(object_counts)

    save_detection_output(first_result, args.output)


if __name__ == "__main__":
    main()
