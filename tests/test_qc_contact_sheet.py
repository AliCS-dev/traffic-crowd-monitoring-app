import numpy as np

from evaluation.qc_contact_sheet import fit_text_scale, letterbox, make_contact_sheet


def test_letterbox_preserves_image_and_target_dimensions():
    image = np.full((50, 100, 3), 255, dtype=np.uint8)

    result = letterbox(image, width=200, height=200)

    assert result.shape == (200, 200, 3)
    assert np.all(result[50:150] == 255)
    assert np.all(result[:50] == 28)


def test_text_scale_reduces_long_labels_to_fit():
    scale = fit_text_scale("a_very_long_asset_identifier", max_width=80)

    assert 0.3 <= scale < 0.5


def test_contact_sheet_has_stable_grid_dimensions():
    image = np.zeros((90, 160, 3), dtype=np.uint8)

    result = make_contact_sheet(
        "test batch",
        [("asset_1", image), ("asset_2", image)],
        columns=2,
        rows=1,
        cell_width=200,
        image_height=100,
    )

    assert result.shape == (178, 400, 3)
