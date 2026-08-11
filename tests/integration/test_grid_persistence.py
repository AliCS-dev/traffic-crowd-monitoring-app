import os
from pathlib import Path

import pytest

from app.database.connection import open_database_connection
from app.database.detection_repository import save_image_detection_results
from app.services.grid_counting_service import count_detections_by_grid

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL integration tests are not enabled.",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = (
    PROJECT_ROOT / "app" / "database" / "migrations" / "001_create_initial_tables.sql"
)


def test_grid_cells_and_summaries_are_persisted_with_correct_relationships():
    detection_records = [
        {
            "object_class": "car",
            "confidence": 0.91,
            "bbox_x_min": 10.0,
            "bbox_y_min": 20.0,
            "bbox_x_max": 50.0,
            "bbox_y_max": 80.0,
        },
        {
            "object_class": "person",
            "confidence": 0.78,
            "bbox_x_min": 120.0,
            "bbox_y_min": 120.0,
            "bbox_x_max": 140.0,
            "bbox_y_max": 180.0,
        },
    ]
    grid_result = count_detections_by_grid(
        detection_records,
        image_width=200,
        image_height=200,
        rows=2,
        columns=2,
    )

    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA_FILE.read_text(encoding="utf-8"))

    stored_result = save_image_detection_results(
        "data/input/integration-grid.jpg",
        image_width=200,
        image_height=200,
        detection_records=detection_records,
        object_count_summary_records=[
            {"object_class": "car", "object_count": 1},
            {"object_class": "person", "object_count": 1},
        ],
        grid_count_result=grid_result,
        session_name="grid persistence integration test",
    )

    try:
        with open_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT row_index, column_index, x_min, y_min, x_max, y_max
                    FROM grid_cells
                    WHERE processed_frame_id = %s
                    ORDER BY row_index, column_index;
                    """,
                    (stored_result["processed_frame_id"],),
                )
                cells = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT
                        grid_cells.row_index,
                        grid_cells.column_index,
                        object_count_summaries.object_class,
                        object_count_summaries.object_count
                    FROM object_count_summaries
                    JOIN grid_cells
                        ON grid_cells.id = object_count_summaries.grid_cell_id
                    WHERE object_count_summaries.processed_frame_id = %s
                    ORDER BY grid_cells.row_index, grid_cells.column_index;
                    """,
                    (stored_result["processed_frame_id"],),
                )
                grid_summaries = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT object_class, object_count
                    FROM object_count_summaries
                    WHERE processed_frame_id = %s
                        AND grid_cell_id IS NULL
                    ORDER BY object_class;
                    """,
                    (stored_result["processed_frame_id"],),
                )
                frame_summaries = cursor.fetchall()
    finally:
        with open_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM monitoring_sessions WHERE id = %s;",
                    (stored_result["session_id"],),
                )

    assert cells == [
        (0, 0, 0, 0, 100, 100),
        (0, 1, 100, 0, 200, 100),
        (1, 0, 0, 100, 100, 200),
        (1, 1, 100, 100, 200, 200),
    ]
    assert grid_summaries == [
        (0, 0, "car", 1),
        (1, 1, "person", 1),
    ]
    assert frame_summaries == [("car", 1), ("person", 1)]
    assert stored_result["grid_cell_count"] == 4
    assert stored_result["grid_object_count_summary_count"] == 2
