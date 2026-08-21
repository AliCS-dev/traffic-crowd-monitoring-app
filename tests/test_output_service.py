from types import SimpleNamespace

import numpy as np
import pytest

from app.services.output_service import save_detection_output


def test_output_write_failure_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.output_service.cv2.imwrite", lambda *_args: False)
    result = SimpleNamespace(plot=lambda: np.zeros((2, 2, 3), dtype=np.uint8))

    with pytest.raises(OSError, match="could not be written"):
        save_detection_output(result, tmp_path / "output.jpg")


def test_detection_output_rejects_dimensions_that_do_not_match_metadata(tmp_path):
    result = SimpleNamespace(plot=lambda: np.zeros((2, 3, 3), dtype=np.uint8))

    with pytest.raises(ValueError, match="do not match processed dimensions"):
        save_detection_output(
            result,
            tmp_path / "output.jpg",
            expected_width=4,
            expected_height=2,
        )

    assert not (tmp_path / "output.jpg").exists()
