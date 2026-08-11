from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from app.database.connection import open_database_connection
from app.services.detection_service import build_object_count_summary_records

if TYPE_CHECKING:
    from app.services.grid_counting_service import GridCountResult
    from app.services.video_detection_service import VideoFrameDetectionResult


def save_image_detection_results(
    image_path,
    image_width,
    image_height,
    detection_records,
    object_count_summary_records=None,
    session_name=None,
    grid_count_result: "GridCountResult | None" = None,
):
    image_path = Path(image_path)
    object_count_summary_records = object_count_summary_records or []
    _validate_grid_image_dimensions(grid_count_result, image_width, image_height)

    grid_cell_count = 0
    grid_object_count_summary_count = 0

    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            session_id = create_monitoring_session(cursor, session_name)
            input_source_id = create_input_source(
                cursor,
                session_id,
                image_path,
                source_type="image",
            )
            processed_frame_id = create_processed_frame(
                cursor,
                session_id,
                input_source_id,
                image_width,
                image_height,
                frame_number=0,
                frame_timestamp_seconds=0,
            )
            create_detection_results(cursor, processed_frame_id, detection_records)
            create_object_count_summaries(
                cursor,
                processed_frame_id,
                object_count_summary_records,
            )
            if grid_count_result is not None:
                (
                    grid_cell_count,
                    grid_object_count_summary_count,
                ) = create_grid_count_results(
                    cursor,
                    processed_frame_id,
                    grid_count_result,
                )
            mark_monitoring_session_completed(cursor, session_id)

    return {
        "session_id": session_id,
        "input_source_id": input_source_id,
        "processed_frame_id": processed_frame_id,
        "detection_count": len(detection_records),
        "object_count_summary_count": len(object_count_summary_records),
        "grid_cell_count": grid_cell_count,
        "grid_object_count_summary_count": grid_object_count_summary_count,
    }


def save_video_detection_results(
    video_path,
    frame_results: Iterable["VideoFrameDetectionResult"],
    session_name=None,
):
    video_path = Path(video_path)
    frame_results = list(frame_results)

    if not frame_results:
        raise ValueError("At least one processed video frame is required.")

    processed_frame_ids = []
    detection_count = 0
    object_count_summary_count = 0

    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            session_id = create_monitoring_session(cursor, session_name)
            input_source_id = create_input_source(
                cursor,
                session_id,
                video_path,
                source_type="video",
            )

            for frame_result in frame_results:
                processed_frame_id = create_processed_frame(
                    cursor,
                    session_id,
                    input_source_id,
                    frame_result.image_width,
                    frame_result.image_height,
                    frame_number=frame_result.frame_number,
                    frame_timestamp_seconds=frame_result.timestamp_seconds,
                )
                processed_frame_ids.append(processed_frame_id)

                create_detection_results(
                    cursor,
                    processed_frame_id,
                    frame_result.detection_records,
                )

                summary_records = build_object_count_summary_records(
                    frame_result.object_counts
                )
                create_object_count_summaries(
                    cursor,
                    processed_frame_id,
                    summary_records,
                )

                detection_count += len(frame_result.detection_records)
                object_count_summary_count += len(summary_records)

            mark_monitoring_session_completed(cursor, session_id)

    return {
        "session_id": session_id,
        "input_source_id": input_source_id,
        "processed_frame_ids": processed_frame_ids,
        "frame_count": len(processed_frame_ids),
        "detection_count": detection_count,
        "object_count_summary_count": object_count_summary_count,
    }


def create_monitoring_session(cursor, session_name):
    cursor.execute(
        """
        INSERT INTO monitoring_sessions (session_name, status)
        VALUES (%s, %s)
        RETURNING id;
        """,
        (session_name, "processing"),
    )

    return cursor.fetchone()[0]


def create_input_source(cursor, session_id, source_path, source_type):
    cursor.execute(
        """
        INSERT INTO input_sources (
            session_id,
            source_type,
            file_path,
            original_filename
        )
        VALUES (%s, %s, %s, %s)
        RETURNING id;
        """,
        (
            session_id,
            source_type,
            str(source_path),
            source_path.name,
        ),
    )

    return cursor.fetchone()[0]


def create_processed_frame(
    cursor,
    session_id,
    input_source_id,
    image_width,
    image_height,
    frame_number,
    frame_timestamp_seconds,
):
    cursor.execute(
        """
        INSERT INTO processed_frames (
            session_id,
            input_source_id,
            frame_number,
            frame_timestamp_seconds,
            image_width,
            image_height
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (
            session_id,
            input_source_id,
            frame_number,
            frame_timestamp_seconds,
            image_width,
            image_height,
        ),
    )

    return cursor.fetchone()[0]


def create_detection_results(cursor, processed_frame_id, detection_records):
    if not detection_records:
        return

    cursor.executemany(
        """
        INSERT INTO detection_results (
            processed_frame_id,
            object_class,
            confidence,
            bbox_x_min,
            bbox_y_min,
            bbox_x_max,
            bbox_y_max
        )
        VALUES (
            %(processed_frame_id)s,
            %(object_class)s,
            %(confidence)s,
            %(bbox_x_min)s,
            %(bbox_y_min)s,
            %(bbox_x_max)s,
            %(bbox_y_max)s
        );
        """,
        [
            {
                "processed_frame_id": processed_frame_id,
                **detection_record,
            }
            for detection_record in detection_records
        ],
    )


def create_object_count_summaries(
    cursor,
    processed_frame_id,
    object_count_summary_records,
):
    if not object_count_summary_records:
        return

    cursor.executemany(
        """
        INSERT INTO object_count_summaries (
            processed_frame_id,
            grid_cell_id,
            object_class,
            object_count
        )
        VALUES (
            %(processed_frame_id)s,
            %(grid_cell_id)s,
            %(object_class)s,
            %(object_count)s
        );
        """,
        [
            {
                "processed_frame_id": processed_frame_id,
                "grid_cell_id": object_count_summary_record.get("grid_cell_id"),
                **object_count_summary_record,
            }
            for object_count_summary_record in object_count_summary_records
        ],
    )


def create_grid_count_results(cursor, processed_frame_id, grid_count_result):
    summary_records = []

    for cell in grid_count_result.cells:
        grid_cell_id = create_grid_cell(cursor, processed_frame_id, cell)
        summary_records.extend(
            {
                "grid_cell_id": grid_cell_id,
                "object_class": object_class,
                "object_count": object_count,
            }
            for object_class, object_count in cell.object_counts.items()
            if object_count > 0
        )

    create_object_count_summaries(
        cursor,
        processed_frame_id,
        summary_records,
    )
    return len(grid_count_result.cells), len(summary_records)


def create_grid_cell(cursor, processed_frame_id, cell):
    cursor.execute(
        """
        INSERT INTO grid_cells (
            processed_frame_id,
            row_index,
            column_index,
            x_min,
            y_min,
            x_max,
            y_max
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (
            processed_frame_id,
            cell.row_index,
            cell.column_index,
            cell.x_min,
            cell.y_min,
            cell.x_max,
            cell.y_max,
        ),
    )
    return cursor.fetchone()[0]


def _validate_grid_image_dimensions(grid_count_result, image_width, image_height):
    if grid_count_result is None:
        return
    if (
        grid_count_result.image_width != image_width
        or grid_count_result.image_height != image_height
    ):
        raise ValueError(
            "Grid dimensions must match the dimensions of the processed image."
        )


def mark_monitoring_session_completed(cursor, session_id):
    cursor.execute(
        """
        UPDATE monitoring_sessions
        SET status = %s,
            completed_at = CURRENT_TIMESTAMP
        WHERE id = %s;
        """,
        ("completed", session_id),
    )
