from pathlib import Path
import cv2


SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png"]


def load_input_image(image_path):
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if path.suffix.lower() not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError("Unsupported image format. Please use JPG, JPEG, or PNG.")

    image = cv2.imread(str(path))

    if image is None:
        raise ValueError("Image could not be loaded.")

    height, width = image.shape[:2]

    print("Image loaded successfully")
    print(f"File name: {path.name}")
    print(f"Width: {width}")
    print(f"Height: {height}")

    return image