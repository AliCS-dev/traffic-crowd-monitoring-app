from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from psycopg.rows import dict_row

from app.crowd_analysis import DenseCrowdAnalysisDecision
from app.database.connection import open_database_connection
from app.database.detection_repository import (
    _validate_grid_image_dimensions,
    _validate_output_reference,
    create_alert_results,
    create_dense_crowd_analysis_result,
    create_detection_results,
    create_grid_count_results,
    create_input_source,
    create_model_run_profile,
    create_monitoring_session,
    create_object_count_summaries,
    create_processed_frame,
)
from app.model_profile import RuntimeModelProfile
from app.schemas.monitoring import VideoAnalysisJobResult
from app.services.detection_service import build_object_count_summary_records
from app.services.video_detection_service import VideoFrameDetectionResult


class VideoJobStateError(RuntimeError):
    """Raised when a video job cannot make the requested state transition."""


@dataclass(frozen=True)
class CreatedVideoJob:
    session_id: int
    input_source_id: int


def create_video_analysis_job(
    *,
    video_path: Path,
    original_filename: str,
    session_name: str | None,
    sampling_interval_seconds: float,
    grid_rows: int | None,
    grid_columns: int | None,
    total_source_frames: int,
    sampled_frames_total: int,
    model_profile: RuntimeModelProfile,
    crowd_analysis_decision: DenseCrowdAnalysisDecision,
    connection_factory: Callable = open_database_connection,
) -> CreatedVideoJob:
    with connection_factory() as connection:
        with connection.cursor() as cursor:
            session_id = create_monitoring_session(cursor, session_name, "queued")
            create_model_run_profile(cursor, session_id, model_profile)
            create_dense_crowd_analysis_result(
                cursor, session_id, crowd_analysis_decision
            )
            input_source_id = create_input_source(
                cursor,
                session_id,
                video_path,
                source_type="video",
                original_filename=original_filename,
            )
            cursor.execute(
                """
                INSERT INTO video_analysis_jobs (
                    session_id, input_source_id, status,
                    sampling_interval_seconds, grid_rows, grid_columns,
                    total_source_frames, sampled_frames_total
                )
                VALUES (%s, %s, 'queued', %s, %s, %s, %s, %s);
                """,
                (
                    session_id,
                    input_source_id,
                    sampling_interval_seconds,
                    grid_rows,
                    grid_columns,
                    total_source_frames,
                    sampled_frames_total,
                ),
            )
    return CreatedVideoJob(session_id=session_id, input_source_id=input_source_id)


def mark_video_job_processing(
    session_id: int,
    *,
    connection_factory: Callable = open_database_connection,
) -> None:
    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE video_analysis_jobs
                SET status = 'processing', started_at = CURRENT_TIMESTAMP
                WHERE session_id = %s AND status = 'queued'
                RETURNING session_id;
                """,
                (session_id,),
            )
            if cursor.fetchone() is None:
                raise VideoJobStateError("Video job is not queued.")
            cursor.execute(
                "UPDATE monitoring_sessions SET status = 'processing' WHERE id = %s;",
                (session_id,),
            )


def update_video_job_progress(
    session_id: int,
    sampled_frames_processed: int,
    *,
    connection_factory: Callable = open_database_connection,
) -> None:
    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE video_analysis_jobs
                SET sampled_frames_processed = %s
                WHERE session_id = %s
                  AND status = 'processing'
                  AND sampled_frames_processed <= %s
                  AND %s <= sampled_frames_total
                RETURNING session_id;
                """,
                (
                    sampled_frames_processed,
                    session_id,
                    sampled_frames_processed,
                    sampled_frames_processed,
                ),
            )
            if cursor.fetchone() is None:
                raise VideoJobStateError("Video job progress cannot be updated.")


def complete_video_analysis_job(
    session_id: int,
    frame_results: Sequence[VideoFrameDetectionResult],
    *,
    connection_factory: Callable = open_database_connection,
) -> None:
    if not frame_results:
        raise ValueError("At least one processed video frame is required.")

    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT input_source_id, sampled_frames_total
                FROM video_analysis_jobs
                WHERE session_id = %s AND status = 'processing'
                FOR UPDATE;
                """,
                (session_id,),
            )
            job = cursor.fetchone()
            if job is None or len(frame_results) != job[1]:
                raise VideoJobStateError(
                    "Video job results do not match the expected frame count."
                )

            for result in frame_results:
                _validate_output_reference(
                    result.output_asset_id,
                    result.output_file_path,
                )
                frame_id = create_processed_frame(
                    cursor,
                    session_id,
                    job[0],
                    result.image_width,
                    result.image_height,
                    result.frame_number,
                    result.timestamp_seconds,
                    output_asset_id=result.output_asset_id,
                    output_file_path=result.output_file_path,
                )
                create_detection_results(cursor, frame_id, result.detection_records)
                create_object_count_summaries(
                    cursor,
                    frame_id,
                    build_object_count_summary_records(result.object_counts),
                )
                if result.grid_count_result is not None:
                    _validate_grid_image_dimensions(
                        result.grid_count_result,
                        result.image_width,
                        result.image_height,
                    )
                    created_grid = create_grid_count_results(
                        cursor, frame_id, result.grid_count_result
                    )
                    grid_cell_ids = created_grid.cell_ids
                else:
                    grid_cell_ids = {}
                create_alert_results(
                    cursor,
                    frame_id,
                    result.alert_records,
                    grid_cell_ids,
                )

            cursor.execute(
                """
                UPDATE video_analysis_jobs
                SET status = 'completed',
                    sampled_frames_processed = sampled_frames_total,
                    finished_at = CURRENT_TIMESTAMP
                WHERE session_id = %s;
                """,
                (session_id,),
            )
            cursor.execute(
                """
                UPDATE monitoring_sessions
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                (session_id,),
            )


def fail_video_analysis_job(
    session_id: int,
    failure_code: str,
    failure_message: str,
    *,
    connection_factory: Callable = open_database_connection,
) -> None:
    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE video_analysis_jobs
                SET status = 'failed', failure_code = %s, failure_message = %s,
                    finished_at = CURRENT_TIMESTAMP
                WHERE session_id = %s AND status IN ('queued', 'processing')
                RETURNING session_id;
                """,
                (failure_code, failure_message, session_id),
            )
            if cursor.fetchone() is None:
                return
            cursor.execute(
                """
                UPDATE monitoring_sessions
                SET status = 'failed', completed_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                (session_id,),
            )


def recover_interrupted_video_jobs(
    *, connection_factory: Callable = open_database_connection
) -> int:
    message = "Processing stopped before this job completed. Please upload it again."
    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE video_analysis_jobs
                SET status = 'failed', failure_code = 'worker_interrupted',
                    failure_message = %s, finished_at = CURRENT_TIMESTAMP
                WHERE status IN ('queued', 'processing')
                RETURNING session_id;
                """,
                (message,),
            )
            session_ids = [row[0] for row in cursor.fetchall()]
            if session_ids:
                cursor.execute(
                    """
                    UPDATE monitoring_sessions
                    SET status = 'failed', completed_at = CURRENT_TIMESTAMP
                    WHERE id = ANY(%s);
                    """,
                    (session_ids,),
                )
    return len(session_ids)


def get_video_analysis_job(
    session_id: int,
    *,
    connection_factory: Callable = open_database_connection,
) -> VideoAnalysisJobResult | None:
    with connection_factory() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT session_id, status, sampling_interval_seconds,
                       grid_rows, grid_columns, total_source_frames,
                       sampled_frames_total, sampled_frames_processed,
                       failure_code, failure_message, queued_at, started_at, finished_at
                FROM video_analysis_jobs
                WHERE session_id = %s;
                """,
                (session_id,),
            )
            row = cursor.fetchone()
    if row is None:
        return None
    row["progress_percent"] = round(
        row["sampled_frames_processed"] * 100 / row["sampled_frames_total"], 2
    )
    return VideoAnalysisJobResult.model_validate(row)
