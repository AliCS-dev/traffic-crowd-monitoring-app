import pytest

from app.services.grid_counting_service import count_detections_by_grid


def detection(object_class, x_min, y_min, x_max, y_max):
    return {
        "object_class": object_class,
        "confidence": 0.9,
        "bbox_x_min": x_min,
        "bbox_y_min": y_min,
        "bbox_x_max": x_max,
        "bbox_y_max": y_max,
    }


def test_detections_are_counted_by_bounding_box_centre():
    records = [
        detection("car", 0, 0, 20, 20),
        detection("car", 10, 10, 30, 30),
        detection("person", 40, 10, 60, 30),
        detection("bus", 10, 40, 30, 60),
        detection("truck", 70, 70, 90, 90),
    ]

    result = count_detections_by_grid(
        records,
        image_width=100,
        image_height=100,
        rows=2,
        columns=2,
    )

    assert len(result.cells) == 4
    assert result.total_count == 5
    assert dict(result.get_cell(0, 0).object_counts) == {"car": 2}
    assert dict(result.get_cell(0, 1).object_counts) == {"person": 1}
    assert dict(result.get_cell(1, 0).object_counts) == {"bus": 1}
    assert dict(result.get_cell(1, 1).object_counts) == {"truck": 1}


def test_internal_boundary_centres_use_the_right_or_lower_cell():
    records = [
        detection("car", 40, 10, 60, 30),
        detection("person", 10, 40, 30, 60),
        detection("bus", 40, 40, 60, 60),
    ]

    result = count_detections_by_grid(
        records,
        image_width=100,
        image_height=100,
        rows=2,
        columns=2,
    )

    assert result.get_cell(0, 0).total_count == 0
    assert dict(result.get_cell(0, 1).object_counts) == {"car": 1}
    assert dict(result.get_cell(1, 0).object_counts) == {"person": 1}
    assert dict(result.get_cell(1, 1).object_counts) == {"bus": 1}


def test_uneven_dimensions_cover_the_complete_image():
    result = count_detections_by_grid(
        [detection("car", 101, 55, 101, 55)],
        image_width=101,
        image_height=55,
        rows=2,
        columns=3,
    )

    final_cell = result.get_cell(1, 2)
    assert final_cell.x_max == 101
    assert final_cell.y_max == 55
    assert dict(final_cell.object_counts) == {"car": 1}


def test_empty_detection_list_returns_stable_empty_cells():
    result = count_detections_by_grid(
        [],
        image_width=640,
        image_height=480,
        rows=3,
        columns=4,
    )

    assert len(result.cells) == 12
    assert result.total_count == 0
    assert all(cell.object_counts == {} for cell in result.cells)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("image_width", 0, "Image width"),
        ("image_height", -1, "Image height"),
        ("rows", 0, "Grid rows"),
        ("columns", True, "Grid columns"),
    ],
)
def test_dimensions_must_be_positive_integers(field, value, message):
    arguments = {
        "image_width": 100,
        "image_height": 100,
        "rows": 2,
        "columns": 2,
    }
    arguments[field] = value

    with pytest.raises(ValueError, match=message):
        count_detections_by_grid([], **arguments)


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ({}, "object_class"),
        (detection("", 10, 10, 20, 20), "object_class"),
        (detection("car", None, 10, 20, 20), "numeric bbox_x_min"),
        (detection("car", float("inf"), 10, 20, 20), "finite bbox_x_min"),
        (detection("car", 30, 10, 20, 20), "horizontal bounds"),
        (detection("car", 10, 10, 101, 20), "horizontal bounds"),
        (detection("car", 10, -1, 20, 20), "vertical bounds"),
    ],
)
def test_invalid_detection_records_are_rejected(record, message):
    with pytest.raises(ValueError, match=message):
        count_detections_by_grid(
            [record],
            image_width=100,
            image_height=100,
            rows=2,
            columns=2,
        )


def test_get_cell_rejects_indices_outside_the_grid():
    result = count_detections_by_grid(
        [],
        image_width=100,
        image_height=100,
        rows=2,
        columns=2,
    )

    with pytest.raises(IndexError, match="row index"):
        result.get_cell(2, 0)
    with pytest.raises(IndexError, match="column index"):
        result.get_cell(0, -1)
