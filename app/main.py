import argparse

from app.config import (
    SAMPLE_IMAGE_PATH,
    SAMPLE_OUTPUT_PATH,
)
from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.database.detection_repository import save_image_detection_results
from app.model_profile import load_runtime_model_profile
from app.services.detection_service import (
    build_object_count_summary_records,
    count_detected_objects,
    detect_objects,
    extract_detection_records,
    print_object_summary,
)
from app.services.grid_counting_service import (
    GridCountResult,
    count_detections_by_grid,
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
        "--save-to-db",
        action="store_true",
        help="Save detection results to the PostgreSQL database.",
    )

    parser.add_argument(
        "--session-name",
        default=None,
        help="Optional name for the monitoring session stored in the database.",
    )

    parser.add_argument(
        "--grid",
        nargs=2,
        type=positive_integer,
        metavar=("ROWS", "COLUMNS"),
        default=None,
        help="Print object counts for a grid with the given rows and columns.",
    )

    return parser.parse_args()


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Grid dimensions must be positive integers.")
    return number


def print_grid_summary(grid_result: GridCountResult) -> None:
    print(
        f"\nGrid Summary ({grid_result.grid_size.rows} rows x "
        f"{grid_result.grid_size.columns} columns)"
    )
    print("------------")
    non_empty_cells = [cell for cell in grid_result.cells if cell.total_count]
    if not non_empty_cells:
        print("No objects assigned to grid cells.")
        return
    for cell in non_empty_cells:
        counts = ", ".join(
            f"{object_class}: {count}"
            for object_class, count in cell.object_counts.items()
        )
        print(f"Row {cell.row_index + 1}, column {cell.column_index + 1}: {counts}")


def print_database_storage_summary(stored_result) -> None:
    print("Detection results saved to database.")
    print(f"Monitoring session ID: {stored_result['session_id']}")
    print(f"Processed frame ID: {stored_result['processed_frame_id']}")
    print(f"Stored detections: {stored_result['detection_count']}")
    print(
        f"Stored object count summaries: {stored_result['object_count_summary_count']}"
    )
    if stored_result["grid_cell_count"]:
        print(f"Stored grid cells: {stored_result['grid_cell_count']}")
        print(
            "Stored grid object count summaries: "
            f"{stored_result['grid_object_count_summary_count']}"
        )


def main():
    args = parse_arguments()
    model_profile = load_runtime_model_profile()
    crowd_analysis_decision = load_dense_crowd_analysis_decision()
    class_mapping = model_profile.class_mapping_dict()

    print(f"Runtime model profile: {model_profile.profile_id}")
    print(f"Model quality-gate status: {model_profile.quality_gate_status}")
    print(f"Dense-crowd counting: {crowd_analysis_decision.status}")
    print("Dense-crowd count: unavailable; no candidate passed evaluation.")

    image = load_input_image(args.image)
    height, width = image.shape[:2]

    print("Image loaded successfully.")
    print(f"Input image: {args.image}")
    print(f"Width: {width}")
    print(f"Height: {height}")
    print("Image is ready for preprocessing.")

    processed_image = preprocess_image_for_detection(
        image, scale_factor=model_profile.scale_factor
    )
    processed_height, processed_width = processed_image.shape[:2]

    print("Image preprocessing completed.")
    print("Image is ready for object detection.")

    results = detect_objects(
        processed_image,
        model_profile,
    )

    first_result = results[0]
    object_counts = count_detected_objects(first_result, class_mapping)
    detection_records = extract_detection_records(first_result, class_mapping)

    print("Object detection completed.")
    print_object_summary(object_counts)

    grid_result = None
    if args.grid:
        grid_rows, grid_columns = args.grid
        grid_result = count_detections_by_grid(
            detection_records,
            image_width=processed_width,
            image_height=processed_height,
            rows=grid_rows,
            columns=grid_columns,
        )
        print_grid_summary(grid_result)

    save_detection_output(first_result, args.output)

    if args.save_to_db:
        object_count_summary_records = build_object_count_summary_records(object_counts)
        stored_result = save_image_detection_results(
            image_path=args.image,
            image_width=processed_width,
            image_height=processed_height,
            detection_records=detection_records,
            object_count_summary_records=object_count_summary_records,
            grid_count_result=grid_result,
            session_name=args.session_name,
            model_profile=model_profile,
            crowd_analysis_decision=crowd_analysis_decision,
        )

        print_database_storage_summary(stored_result)


if __name__ == "__main__":
    main()
