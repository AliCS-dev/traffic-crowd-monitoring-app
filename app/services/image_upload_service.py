from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import cv2
import numpy as np
from PIL import Image, JpegImagePlugin, PngImagePlugin

READ_CHUNK_SIZE = 64 * 1024
FORMAT_BY_SUFFIX = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
}
MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
}
IMAGE_CLASS_BY_FORMAT = {
    "JPEG": JpegImagePlugin.JpegImageFile,
    "PNG": PngImagePlugin.PngImageFile,
}


class ImageUploadError(ValueError):
    """Base class for upload validation failures."""


class UnsupportedImageUploadError(ImageUploadError):
    """Raised when declared or detected image formats are unsupported."""


class ImageUploadTooLargeError(ImageUploadError):
    """Raised when encoded bytes or decoded pixels exceed configured limits."""


class InvalidImageUploadError(ImageUploadError):
    """Raised when uploaded bytes do not decode into a valid image."""


@dataclass(frozen=True)
class ImageUploadPolicy:
    max_bytes: int
    max_pixels: int

    def __post_init__(self) -> None:
        if self.max_bytes < 1 or self.max_pixels < 1:
            raise ValueError("Image upload limits must be positive integers.")


@dataclass(frozen=True)
class ValidatedImageUpload:
    original_filename: str
    suffix: str
    content: bytes
    image: np.ndarray


def validate_image_upload(
    file: BinaryIO,
    *,
    filename: str | None,
    content_type: str | None,
    policy: ImageUploadPolicy,
) -> ValidatedImageUpload:
    original_filename = _safe_original_filename(filename)
    suffix = Path(original_filename).suffix.lower()
    expected_format = FORMAT_BY_SUFFIX.get(suffix)
    if expected_format is None:
        raise UnsupportedImageUploadError(
            "Only JPG, JPEG, and PNG image uploads are supported."
        )
    if content_type != MIME_BY_FORMAT[expected_format]:
        raise UnsupportedImageUploadError(
            "The uploaded image MIME type does not match its extension."
        )

    content = _read_bounded(file, policy.max_bytes)
    detected_format, width, height = _inspect_image(content)
    if detected_format != expected_format:
        raise UnsupportedImageUploadError(
            "The uploaded image content does not match its extension."
        )
    if width * height > policy.max_pixels:
        raise ImageUploadTooLargeError(
            "The decoded image dimensions exceed the configured pixel limit."
        )

    encoded = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise InvalidImageUploadError("The uploaded file is not a valid image.")
    decoded_height, decoded_width = image.shape[:2]
    if (decoded_width, decoded_height) != (width, height):
        raise InvalidImageUploadError("The uploaded image dimensions are inconsistent.")

    return ValidatedImageUpload(
        original_filename=original_filename,
        suffix=suffix,
        content=content,
        image=image,
    )


def _safe_original_filename(filename: str | None) -> str:
    if not filename:
        raise UnsupportedImageUploadError("The image upload must have a filename.")
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not basename or len(basename) > 255 or any(ord(char) < 32 for char in basename):
        raise UnsupportedImageUploadError("The image filename is invalid.")
    return basename


def _read_bounded(file: BinaryIO, max_bytes: int) -> bytes:
    chunks = []
    total_bytes = 0
    while True:
        chunk = file.read(min(READ_CHUNK_SIZE, max_bytes + 1 - total_bytes))
        if not chunk:
            break
        chunks.append(chunk)
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise ImageUploadTooLargeError(
                "The image upload exceeds the configured file-size limit."
            )
    if total_bytes == 0:
        raise InvalidImageUploadError("The uploaded image is empty.")
    return b"".join(chunks)


def _inspect_image(content: bytes) -> tuple[str, int, int]:
    for detected_format, image_class in IMAGE_CLASS_BY_FORMAT.items():
        try:
            with image_class(BytesIO(content)) as image:
                width, height = image.size
                image.verify()
        except (
            Image.DecompressionBombError,
            OSError,
            SyntaxError,
            ValueError,
        ):
            continue
        if width > 0 and height > 0:
            return detected_format, width, height
    raise InvalidImageUploadError("The uploaded file is not a valid image.")
