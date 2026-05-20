import cv2


def preprocess_image_for_detection(image, scale_factor=3):
    """

    This function increases the image size to make small objects easier for YOLO to detect.
    """

    height, width = image.shape[:2]

    new_width = width * scale_factor
    new_height = height * scale_factor

    resized_image = cv2.resize(
        image,
        (new_width, new_height),
        interpolation=cv2.INTER_CUBIC
    )

    return resized_image