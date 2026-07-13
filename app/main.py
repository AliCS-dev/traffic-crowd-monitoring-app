import argparse

from app.config import MODEL_PATH, SAMPLE_IMAGE_PATH, SAMPLE_OUTPUT_PATH
from app.database.detection_repository import save_image_detection_results
from app.services.detection_service import (
    build_object_count_summary_records,
    count_detected_objects,
    detect_objects,
    extract_detection_records,
    print_object_summary,
)
from app.services.image_service import load_input_image
from app.services.output_service import save_detection_output
from app.services.preprocessing_service import preprocess_image_for_detection


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run object detection on an input image."
    )

    parser.add_argument(
        "--image", default=SAMPLE_IMAGE_PATH, help="Path to the input image."
    )

    parser.add_argument(
        "--output",
        default=SAMPLE_OUTPUT_PATH,
        help="Path where the annotated output image will be saved.",
    )

    parser.add_argument(
        "--confidence",
        type=float,
        default=0.10,
        help="Minimum detection confidence threshold.",
    )

    parser.add_argument(
        "--image-size", type=int, default=1280, help="YOLO inference image size."
    )

    parser.add_argument(
        "--scale-factor",
        type=int,
        default=2,
        help="Image resize scale factor before detection.",
    )

    parser.add_argument(
        "--save-to-db",
        action="store_true",
        help="Save detection results to the PostgreSQL database.",
    )

    parser.add_argument(
        "--session-name",
        default=None,
        help="Optional name for the monitoring session stored in the database.",
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
        image, scale_factor=args.scale_factor
    )
    processed_height, processed_width = processed_image.shape[:2]

    print("Image preprocessing completed.")
    print("Image is ready for object detection.")

    results = detect_objects(
        processed_image,
        MODEL_PATH,
        confidence_threshold=args.confidence,
        image_size=args.image_size,
    )

    first_result = results[0]
    object_counts = count_detected_objects(first_result)

    print("Object detection completed.")
    print_object_summary(object_counts)

    save_detection_output(first_result, args.output)

    if args.save_to_db:
        detection_records = extract_detection_records(first_result)
        object_count_summary_records = build_object_count_summary_records(object_counts)
        stored_result = save_image_detection_results(
            image_path=args.image,
            image_width=processed_width,
            image_height=processed_height,
            detection_records=detection_records,
            object_count_summary_records=object_count_summary_records,
            session_name=args.session_name,
        )

        print("Detection results saved to database.")
        print(f"Monitoring session ID: {stored_result['session_id']}")
        print(f"Processed frame ID: {stored_result['processed_frame_id']}")
        print(f"Stored detections: {stored_result['detection_count']}")
        print(
            "Stored object count summaries: "
            f"{stored_result['object_count_summary_count']}"
        )


if __name__ == "__main__":
    main()
