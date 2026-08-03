from pathlib import Path

import cv2
import numpy as np
import pytest

from evaluation.annotation_conversion import (
    clip_xyxy,
    convert_yolo_line,
    count_point_mask,
    parse_okutama_line,
)
from evaluation.manual_annotation_import import validated_bbox


def test_yolo_box_is_converted_to_coco_pixels():
    box = convert_yolo_line("0 0.5 0.5 0.25 0.5", width=200, height=100)

    assert box.category_id == 4
    assert box.bbox == pytest.approx((75.0, 25.0, 50.0, 50.0))


def test_clipping_keeps_box_inside_image():
    assert clip_xyxy(-5, 10, 105, 90, width=100, height=80) == (
        0.0,
        10,
        100.0,
        70.0,
    )


def test_okutama_box_is_scaled_and_lost_box_is_skipped():
    visible = '7 300 600 600 900 42 0 1 1 "Person" "Walking"'
    lost = '7 300 600 600 900 42 1 0 0 "Person" "Walking"'

    frame, box = parse_okutama_line(visible, width=1280, height=720)
    lost_frame, lost_box = parse_okutama_line(lost, width=1280, height=720)

    assert frame == 42
    assert box is not None
    assert box.bbox == pytest.approx((100.0, 200.0, 100.0, 100.0))
    assert box.source_attributes["occluded"] is True
    assert lost_frame == 42
    assert lost_box is None


def test_dlr_point_mask_counts_nonzero_pixels(tmp_path: Path):
    mask = np.array([[0, 255, 0], [255, 0, 255]], dtype=np.uint8)
    path = tmp_path / "mask.png"
    assert cv2.imwrite(str(path), mask)

    assert count_point_mask(path) == 3


def test_dlr_point_mask_rejects_non_binary_values(tmp_path: Path):
    mask = np.array([[0, 128, 255]], dtype=np.uint8)
    path = tmp_path / "mask.png"
    assert cv2.imwrite(str(path), mask)

    with pytest.raises(ValueError, match="not binary"):
        count_point_mask(path)


def test_rotated_manual_box_is_normalised_and_clipped_to_image():
    annotation = {
        "id": 7,
        "bbox": [80, 70, 20, 20],
        "iscrowd": 0,
        "attributes": {"rotation": 45},
    }

    bbox, rotation = validated_bbox(annotation, width=100, height=80)

    assert bbox == pytest.approx((75.857864, 65.857864, 24.142136, 14.142136))
    assert rotation == 45
