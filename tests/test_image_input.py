import pytest
from app.services.image_service import load_input_image


def test_missing_image_file_raises_error():
    with pytest.raises(FileNotFoundError):
        load_input_image("data/input/missing_image.jpg")


def test_unsupported_image_format_raises_error(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("This is not an image.")

    with pytest.raises(ValueError):
        load_input_image(str(test_file))
