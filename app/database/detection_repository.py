from pathlib import Path

from app.database.connection import open_database_connection


def save_image_detection_results(
    image_path,
    image_width,
    image_height,
    detection_records,
    session_name=None,
):
    image_path = Path(image_path)

    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            session_id = create_monitoring_session(cursor, session_name)
            input_source_id = create_input_source(cursor, session_id, image_path)
            processed_frame_id = create_processed_frame(
                cursor,
                session_id,
                input_source_id,
                image_width,
                image_height,
            )
            create_detection_results(cursor, processed_frame_id, detection_records)
            mark_monitoring_session_completed(cursor, session_id)

    return {
        "session_id": session_id,
        "input_source_id": input_source_id,
        "processed_frame_id": processed_frame_id,
        "detection_count": len(detection_records),
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


def create_input_source(cursor, session_id, image_path):
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
            "image",
            str(image_path),
            image_path.name,
        ),
    )

    return cursor.fetchone()[0]


def create_processed_frame(
    cursor,
    session_id,
    input_source_id,
    image_width,
    image_height,
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
            0,
            0,
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
