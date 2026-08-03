from pathlib import Path

import numpy as np

from evaluation.annotation_preview import (
    apply_exif_orientation,
    box_iou,
    box_quality_flags,
    class_conflict_box_pairs,
    draw_boxes,
    draw_point_mask,
    duplicate_box_pairs,
    remove_stale_previews,
    resize_for_preview,
)


def test_resize_for_preview_preserves_aspect_ratio():
    image = np.zeros((100, 200, 3), dtype=np.uint8)

    resized = resize_for_preview(image, max_width=100)

    assert resized.shape == (50, 100, 3)


def test_draw_boxes_changes_pixels_around_box():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    annotations = [{"bbox": [10, 20, 30, 40], "category_id": 4}]

    preview = draw_boxes(image, annotations)

    assert np.count_nonzero(preview) > 0


def test_box_iou_detects_duplicate_boxes():
    assert box_iou([10, 10, 20, 20], [10, 10, 20, 20]) == 1
    assert box_iou([10, 10, 20, 20], [40, 40, 10, 10]) == 0


def test_duplicate_box_pairs_reports_matching_class_and_iou():
    annotations = [
        {"id": 1, "bbox": [10, 10, 20, 20], "category_id": 4},
        {"id": 2, "bbox": [10, 10, 20, 20], "category_id": 4},
        {"id": 3, "bbox": [10, 10, 20, 20], "category_id": 5},
    ]

    pairs = duplicate_box_pairs(annotations)

    assert [(first["id"], second["id"], iou) for first, second, iou in pairs] == [
        (1, 2, 1.0)
    ]


def test_class_conflict_box_pairs_reports_overlapping_different_classes():
    annotations = [
        {"id": 1, "bbox": [10, 10, 20, 20], "category_id": 4},
        {"id": 2, "bbox": [10, 10, 20, 20], "category_id": 5},
    ]

    pairs = class_conflict_box_pairs(annotations)

    assert [(first["id"], second["id"], iou) for first, second, iou in pairs] == [
        (1, 2, 1.0)
    ]


def test_box_quality_flags_report_structural_review_items():
    annotations = [
        {"bbox": [0, 10, 20, 20], "category_id": 4},
        {"bbox": [0, 10, 20, 20], "category_id": 4},
        {"bbox": [50, 50, 3, 3], "category_id": 1},
        {"bbox": [10, 10, 40, 40], "category_id": 5},
    ]

    flags = box_quality_flags(annotations, width=100, height=100)

    assert flags == {
        "duplicate_pairs": 1,
        "class_conflict_pairs": 0,
        "edge_boxes": 2,
        "very_small_boxes": 1,
        "unusually_large_boxes": 1,
    }


def test_draw_point_mask_marks_person_points():
    image = np.zeros((20, 20, 3), dtype=np.uint8)
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[10, 10] = 255

    preview = draw_point_mask(image, mask)

    assert preview[10, 10, 2] > 0


def test_exif_orientation_eight_rotates_mask_counterclockwise():
    mask = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint8)

    oriented = apply_exif_orientation(mask, orientation=8)

    assert oriented.tolist() == [[3, 6], [2, 5], [1, 4]]


def test_remove_stale_previews_keeps_only_expected_files(tmp_path: Path):
    expected = tmp_path / "validation" / "expected.jpg"
    stale = tmp_path / "held_out_test" / "stale.jpg"
    expected.parent.mkdir(parents=True)
    stale.parent.mkdir(parents=True)
    expected.write_bytes(b"expected")
    stale.write_bytes(b"stale")

    remove_stale_previews(tmp_path, {expected})

    assert expected.is_file()
    assert not stale.exists()
