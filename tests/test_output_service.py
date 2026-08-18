from types import SimpleNamespace

import numpy as np
import pytest

from app.services.output_service import save_detection_output


def test_output_write_failure_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.output_service.cv2.imwrite", lambda *_args: False)
    result = SimpleNamespace(plot=lambda: np.zeros((2, 2, 3), dtype=np.uint8))

    with pytest.raises(OSError, match="could not be written"):
        save_detection_output(result, tmp_path / "output.jpg")
