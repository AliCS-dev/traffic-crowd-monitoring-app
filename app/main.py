from app.services.image_service import load_input_image
from app.services.detection_service import detect_objects
from app.services.output_service import save_detection_output
from app.config import MODEL_PATH, SAMPLE_IMAGE_PATH, SAMPLE_OUTPUT_PATH


def main():
    image = load_input_image(SAMPLE_IMAGE_PATH)

    print("Image is ready for the next processing step.")

    results = detect_objects(image, MODEL_PATH)

    first_result = results[0]
    number_of_detections = len(first_result.boxes)

    print("Object detection completed.")
    print(f"Number of detections: {number_of_detections}")

    save_detection_output(first_result, SAMPLE_OUTPUT_PATH)


if __name__ == "__main__":
    main()