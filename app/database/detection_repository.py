import json
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from app.crowd_analysis import DenseCrowdAnalysisDecision
from app.database.connection import open_database_connection
from app.model_profile import RuntimeModelProfile
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
    *,
    model_profile: RuntimeModelProfile,
    crowd_analysis_decision: DenseCrowdAnalysisDecision,
    original_filename=None,
    output_asset_id=None,
    output_file_path=None,
):
    image_path = Path(image_path)
    object_count_summary_records = object_count_summary_records or []
    _validate_grid_image_dimensions(grid_count_result, image_width, image_height)
    _validate_output_reference(output_asset_id, output_file_path)

    grid_cell_count = 0
    grid_object_count_summary_count = 0

    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            session_id = create_monitoring_session(cursor, session_name)
            create_model_run_profile(cursor, session_id, model_profile)
            create_dense_crowd_analysis_result(
                cursor,
                session_id,
                crowd_analysis_decision,
            )
            input_source_id = create_input_source(
                cursor,
                session_id,
                image_path,
                source_type="image",
                original_filename=original_filename,
            )
            processed_frame_id = create_processed_frame(
                cursor,
                session_id,
                input_source_id,
                image_width,
                image_height,
                frame_number=0,
                frame_timestamp_seconds=0,
                output_asset_id=output_asset_id,
                output_file_path=output_file_path,
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
    *,
    model_profile: RuntimeModelProfile,
    crowd_analysis_decision: DenseCrowdAnalysisDecision,
):
    video_path = Path(video_path)
    frame_results = list(frame_results)

    if not frame_results:
        raise ValueError("At least one processed video frame is required.")

    processed_frame_ids = []
    detection_count = 0
    object_count_summary_count = 0
    grid_cell_count = 0
    grid_object_count_summary_count = 0

    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            session_id = create_monitoring_session(cursor, session_name)
            create_model_run_profile(cursor, session_id, model_profile)
            create_dense_crowd_analysis_result(
                cursor,
                session_id,
                crowd_analysis_decision,
            )
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

                if frame_result.grid_count_result is not None:
                    _validate_grid_image_dimensions(
                        frame_result.grid_count_result,
                        frame_result.image_width,
                        frame_result.image_height,
                    )
                    cell_count, grid_summary_count = create_grid_count_results(
                        cursor,
                        processed_frame_id,
                        frame_result.grid_count_result,
                    )
                    grid_cell_count += cell_count
                    grid_object_count_summary_count += grid_summary_count

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
        "grid_cell_count": grid_cell_count,
        "grid_object_count_summary_count": grid_object_count_summary_count,
    }


def create_monitoring_session(cursor, session_name, status="processing"):
    cursor.execute(
        """
        INSERT INTO monitoring_sessions (session_name, status)
        VALUES (%s, %s)
        RETURNING id;
        """,
        (session_name, status),
    )

    return cursor.fetchone()[0]


def create_model_run_profile(cursor, session_id, model_profile):
    cursor.execute(
        """
        INSERT INTO model_run_profiles (
            session_id,
            profile_id,
            model_id,
            quality_gate_status,
            evaluation_reference,
            checkpoint_path,
            checkpoint_sha256,
            class_mapping,
            confidence,
            image_size,
            scale_factor,
            max_detections,
            numeric_precision,
            device
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSONB),
            %s, %s, %s, %s, %s, %s
        );
        """,
        (
            session_id,
            model_profile.profile_id,
            model_profile.model_id,
            model_profile.quality_gate_status,
            model_profile.evaluation_reference.as_posix(),
            model_profile.checkpoint_path.as_posix(),
            model_profile.checkpoint_sha256,
            json.dumps(model_profile.class_mapping_dict(), sort_keys=True),
            model_profile.confidence,
            model_profile.image_size,
            model_profile.scale_factor,
            model_profile.max_detections,
            model_profile.numeric_precision,
            model_profile.device,
        ),
    )


def create_dense_crowd_analysis_result(cursor, session_id, decision):
    cursor.execute(
        """
        INSERT INTO dense_crowd_analysis_results (
            session_id,
            status,
            crowd_count,
            method_id,
            model_id,
            evaluated_candidate_id,
            quality_gate_status,
            evaluation_reference,
            reason_code,
            message
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        (
            session_id,
            decision.status,
            decision.count,
            decision.method_id,
            decision.model_id,
            decision.evaluated_candidate_id,
            decision.quality_gate_status,
            decision.evaluation_reference.as_posix(),
            decision.reason_code,
            decision.message,
        ),
    )


def create_input_source(
    cursor,
    session_id,
    source_path,
    source_type,
    original_filename=None,
):
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
            original_filename or source_path.name,
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
    output_asset_id=None,
    output_file_path=None,
):
    cursor.execute(
        """
        INSERT INTO processed_frames (
            session_id,
            input_source_id,
            frame_number,
            frame_timestamp_seconds,
            image_width,
            image_height,
            output_asset_id,
            output_file_path
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (
            session_id,
            input_source_id,
            frame_number,
            frame_timestamp_seconds,
            image_width,
            image_height,
            output_asset_id,
            str(output_file_path) if output_file_path is not None else None,
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


def _validate_output_reference(output_asset_id, output_file_path):
    if (output_asset_id is None) != (output_file_path is None):
        raise ValueError(
            "Output asset ID and output file path must be provided together."
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
