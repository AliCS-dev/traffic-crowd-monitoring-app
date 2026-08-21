import argparse

import pytest

from app.main import (
    positive_integer,
    print_database_storage_summary,
    print_grid_summary,
)
from app.services.grid_counting_service import count_detections_by_grid


def test_grid_summary_prints_only_occupied_cells(capsys):
    result = count_detections_by_grid(
        [
            {
                "object_class": "car",
                "bbox_x_min": 10,
                "bbox_y_min": 10,
                "bbox_x_max": 30,
                "bbox_y_max": 30,
            }
        ],
        image_width=100,
        image_height=100,
        rows=2,
        columns=2,
    )

    print_grid_summary(result)

    assert capsys.readouterr().out == (
        "\nGrid Summary (2 rows x 2 columns)\n------------\nRow 1, column 1: car: 1\n"
    )


def test_empty_grid_summary_has_clear_output(capsys):
    result = count_detections_by_grid(
        [],
        image_width=100,
        image_height=100,
        rows=2,
        columns=2,
    )

    print_grid_summary(result)

    assert "No objects assigned to grid cells." in capsys.readouterr().out


def test_grid_command_dimensions_must_be_positive():
    assert positive_integer("3") == 3

    with pytest.raises(argparse.ArgumentTypeError, match="positive integers"):
        positive_integer("0")


def test_database_summary_reports_persisted_grid_results(capsys):
    print_database_storage_summary(
        {
            "session_id": 10,
            "processed_frame_id": 30,
            "detection_count": 2,
            "object_count_summary_count": 2,
            "grid_cell_count": 4,
            "grid_object_count_summary_count": 2,
            "alert_count": 1,
        }
    )

    output = capsys.readouterr().out
    assert "Stored grid cells: 4" in output
    assert "Stored grid object count summaries: 2" in output
    assert "Stored experimental alerts: 1" in output
