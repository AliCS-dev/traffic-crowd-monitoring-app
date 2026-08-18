from io import BytesIO

import cv2
import numpy as np
import pytest

from app.services.image_upload_service import (
    ImageUploadPolicy,
    ImageUploadTooLargeError,
    InvalidImageUploadError,
    UnsupportedImageUploadError,
    validate_image_upload,
)


def encoded_image(extension=".jpg", *, width=4, height=3):
    image = np.full((height, width, 3), 127, dtype=np.uint8)
    success, encoded = cv2.imencode(extension, image)
    assert success
    return encoded.tobytes()


def policy(*, max_bytes=1024 * 1024, max_pixels=1000):
    return ImageUploadPolicy(max_bytes=max_bytes, max_pixels=max_pixels)


def test_valid_upload_is_decoded_and_original_path_is_removed():
    content = encoded_image(".jpg")

    result = validate_image_upload(
        BytesIO(content),
        filename="C:\\fakepath\\junction.JPEG",
        content_type="image/jpeg",
        policy=policy(),
    )

    assert result.original_filename == "junction.JPEG"
    assert result.suffix == ".jpeg"
    assert result.content == content
    assert result.image.shape == (3, 4, 3)


class FailOnRead:
    def read(self, _size):
        pytest.fail("Unsupported metadata should be rejected before reading bytes.")


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [("scene.gif", "image/gif"), ("scene.jpg", "text/plain"), (None, "image/jpeg")],
)
def test_unsupported_metadata_is_rejected_before_file_read(filename, content_type):
    with pytest.raises(UnsupportedImageUploadError):
        validate_image_upload(
            FailOnRead(),
            filename=filename,
            content_type=content_type,
            policy=policy(),
        )


def test_upload_larger_than_limit_is_rejected():
    content = encoded_image(".png")

    with pytest.raises(ImageUploadTooLargeError, match="file-size limit"):
        validate_image_upload(
            BytesIO(content),
            filename="scene.png",
            content_type="image/png",
            policy=policy(max_bytes=len(content) - 1),
        )


def test_content_format_must_match_extension_and_mime():
    with pytest.raises(UnsupportedImageUploadError, match="content"):
        validate_image_upload(
            BytesIO(encoded_image(".png")),
            filename="renamed.jpg",
            content_type="image/jpeg",
            policy=policy(),
        )


@pytest.mark.parametrize("content", [b"", b"not an image"])
def test_empty_or_malformed_image_is_rejected(content):
    with pytest.raises(InvalidImageUploadError):
        validate_image_upload(
            BytesIO(content),
            filename="scene.jpg",
            content_type="image/jpeg",
            policy=policy(),
        )


def test_decoded_pixel_limit_is_enforced_before_opencv_decode():
    with pytest.raises(ImageUploadTooLargeError, match="pixel limit"):
        validate_image_upload(
            BytesIO(encoded_image(".png", width=20, height=10)),
            filename="large.png",
            content_type="image/png",
            policy=policy(max_pixels=199),
        )
