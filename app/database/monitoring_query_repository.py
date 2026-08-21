from collections.abc import Callable
from math import ceil

from psycopg.rows import dict_row

from app.database.connection import open_database_connection
from app.schemas.monitoring import (
    AlertResult,
    DenseCrowdAnalysisResult,
    DetectionResult,
    GridCellResult,
    ImageBounds,
    InputSourceResult,
    ModelRunProfileResult,
    MonitoringSessionPage,
    MonitoringSessionResult,
    MonitoringSessionSummary,
    ObjectCountSummaryResult,
    Pagination,
    PixelCoordinateSpace,
    ProcessedFrameResult,
    VisualAssetReference,
)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class InvalidPaginationError(ValueError):
    """Raised when session history pagination is outside supported bounds."""


class InvalidSessionIdError(ValueError):
    """Raised when a session identifier is not a positive integer."""


def list_monitoring_sessions(
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    connection_factory: Callable | None = None,
) -> MonitoringSessionPage:
    _validate_pagination(page, page_size)
    connection_factory = connection_factory or open_database_connection
    offset = (page - 1) * page_size

    with connection_factory() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT COUNT(*) AS total_items FROM monitoring_sessions;")
            total_items = cursor.fetchone()["total_items"]
            cursor.execute(
                """
                SELECT id, session_name, status, started_at, completed_at
                FROM monitoring_sessions
                ORDER BY started_at DESC, id DESC
                LIMIT %s OFFSET %s;
                """,
                (page_size, offset),
            )
            rows = cursor.fetchall()

    return MonitoringSessionPage(
        items=[MonitoringSessionSummary.model_validate(row) for row in rows],
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=ceil(total_items / page_size),
        ),
    )


def get_monitoring_session(
    session_id: int,
    *,
    connection_factory: Callable | None = None,
) -> MonitoringSessionResult | None:
    _validate_session_id(session_id)
    connection_factory = connection_factory or open_database_connection

    with connection_factory() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            session_row = _load_session(cursor, session_id)
            if session_row is None:
                return None

            crowd_analysis_row = _load_dense_crowd_analysis(cursor, session_id)
            source_rows = _load_sources(cursor, session_id)
            frame_rows = _load_frames(cursor, session_id)
            frame_data = _prepare_frames(frame_rows)
            if frame_data:
                frame_ids = list(frame_data)
                _attach_detections(cursor, frame_ids, frame_data)
                grid_cells = _attach_grid_cells(cursor, frame_ids, frame_data)
                _attach_summaries(cursor, frame_ids, frame_data, grid_cells)
                _attach_alerts(cursor, frame_ids, frame_data)

    return MonitoringSessionResult(
        id=session_row["id"],
        session_name=session_row["session_name"],
        status=session_row["status"],
        started_at=session_row["started_at"],
        completed_at=session_row["completed_at"],
        notes=session_row["notes"],
        model_profile=_build_model_profile(session_row),
        dense_crowd_analysis=_build_dense_crowd_analysis(crowd_analysis_row),
        sources=[InputSourceResult.model_validate(row) for row in source_rows],
        frames=[_build_frame(values) for values in frame_data.values()],
    )


def _load_session(cursor, session_id):
    cursor.execute(
        """
        SELECT
            sessions.id,
            sessions.session_name,
            sessions.status,
            sessions.started_at,
            sessions.completed_at,
            sessions.notes,
            profiles.profile_id,
            profiles.model_id,
            profiles.quality_gate_status,
            profiles.evaluation_reference,
            profiles.checkpoint_path,
            profiles.checkpoint_sha256,
            profiles.class_mapping,
            profiles.confidence,
            profiles.image_size,
            profiles.scale_factor,
            profiles.max_detections,
            profiles.numeric_precision,
            profiles.device,
            profiles.created_at AS profile_created_at
        FROM monitoring_sessions AS sessions
        LEFT JOIN model_run_profiles AS profiles
            ON profiles.session_id = sessions.id
        WHERE sessions.id = %s;
        """,
        (session_id,),
    )
    return cursor.fetchone()


def _load_sources(cursor, session_id):
    cursor.execute(
        """
        SELECT id, source_type, original_filename, created_at
        FROM input_sources
        WHERE session_id = %s
        ORDER BY created_at, id;
        """,
        (session_id,),
    )
    return cursor.fetchall()


def _load_dense_crowd_analysis(cursor, session_id):
    cursor.execute(
        """
        SELECT
            status,
            crowd_count AS count,
            method_id,
            model_id,
            evaluated_candidate_id,
            quality_gate_status,
            evaluation_reference,
            reason_code,
            message
        FROM dense_crowd_analysis_results
        WHERE session_id = %s;
        """,
        (session_id,),
    )
    return cursor.fetchone()


def _load_frames(cursor, session_id):
    cursor.execute(
        """
        SELECT
            id,
            input_source_id,
            frame_number,
            frame_timestamp_seconds,
            image_width,
            image_height,
            output_asset_id,
            processed_at
        FROM processed_frames
        WHERE session_id = %s
        ORDER BY input_source_id, frame_number, id;
        """,
        (session_id,),
    )
    return cursor.fetchall()


def _prepare_frames(frame_rows):
    return {
        row["id"]: {
            "row": row,
            "detections": [],
            "frame_summaries": [],
            "grid_cells": [],
            "alerts": [],
        }
        for row in frame_rows
    }


def _attach_detections(cursor, frame_ids, frame_data):
    cursor.execute(
        """
        SELECT
            id,
            processed_frame_id,
            object_class,
            confidence,
            bbox_x_min,
            bbox_y_min,
            bbox_x_max,
            bbox_y_max,
            created_at
        FROM detection_results
        WHERE processed_frame_id = ANY(%s)
        ORDER BY processed_frame_id, id;
        """,
        (frame_ids,),
    )
    for row in cursor.fetchall():
        frame_data[row["processed_frame_id"]]["detections"].append(
            DetectionResult(
                id=row["id"],
                object_class=row["object_class"],
                confidence=row["confidence"],
                bounds=_build_bounds(row, prefix="bbox_"),
                created_at=row["created_at"],
            )
        )


def _attach_grid_cells(cursor, frame_ids, frame_data):
    cursor.execute(
        """
        SELECT
            id,
            processed_frame_id,
            row_index,
            column_index,
            x_min,
            y_min,
            x_max,
            y_max
        FROM grid_cells
        WHERE processed_frame_id = ANY(%s)
        ORDER BY processed_frame_id, row_index, column_index, id;
        """,
        (frame_ids,),
    )
    grid_cells = {}
    for row in cursor.fetchall():
        values = {
            "id": row["id"],
            "row_index": row["row_index"],
            "column_index": row["column_index"],
            "bounds": _build_bounds(row),
            "summaries": [],
        }
        grid_cells[row["id"]] = values
        frame_data[row["processed_frame_id"]]["grid_cells"].append(values)
    return grid_cells


def _attach_summaries(cursor, frame_ids, frame_data, grid_cells):
    cursor.execute(
        """
        SELECT
            id,
            processed_frame_id,
            grid_cell_id,
            object_class,
            object_count,
            created_at
        FROM object_count_summaries
        WHERE processed_frame_id = ANY(%s)
        ORDER BY processed_frame_id, grid_cell_id NULLS FIRST, object_class, id;
        """,
        (frame_ids,),
    )
    for row in cursor.fetchall():
        summary = ObjectCountSummaryResult(
            id=row["id"],
            object_class=row["object_class"],
            object_count=row["object_count"],
            created_at=row["created_at"],
        )
        if row["grid_cell_id"] is None:
            frame_data[row["processed_frame_id"]]["frame_summaries"].append(summary)
        else:
            grid_cells[row["grid_cell_id"]]["summaries"].append(summary)


def _attach_alerts(cursor, frame_ids, frame_data):
    cursor.execute(
        """
        SELECT
            id,
            processed_frame_id,
            grid_cell_id,
            alert_type,
            severity,
            message,
            measured_value,
            threshold_value,
            created_at,
            resolved_at
        FROM alerts
        WHERE processed_frame_id = ANY(%s)
        ORDER BY processed_frame_id, created_at, id;
        """,
        (frame_ids,),
    )
    for row in cursor.fetchall():
        frame_data[row["processed_frame_id"]]["alerts"].append(
            AlertResult(
                id=row["id"],
                grid_cell_id=row["grid_cell_id"],
                alert_type=row["alert_type"],
                severity=row["severity"],
                message=row["message"],
                measured_value=row["measured_value"],
                threshold_value=row["threshold_value"],
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
            )
        )


def _build_model_profile(row):
    if row["profile_id"] is None:
        return None
    return ModelRunProfileResult(
        profile_id=row["profile_id"],
        model_id=row["model_id"],
        quality_gate_status=row["quality_gate_status"],
        evaluation_reference=row["evaluation_reference"],
        checkpoint_path=row["checkpoint_path"],
        checkpoint_sha256=row["checkpoint_sha256"],
        class_mapping=row["class_mapping"],
        confidence=row["confidence"],
        image_size=row["image_size"],
        scale_factor=row["scale_factor"],
        max_detections=row["max_detections"],
        numeric_precision=row["numeric_precision"],
        device=row["device"],
        created_at=row["profile_created_at"],
    )


def _build_dense_crowd_analysis(row):
    if row is None:
        return None
    return DenseCrowdAnalysisResult.model_validate(row)


def _build_bounds(row, prefix=""):
    return ImageBounds(
        x_min=row[f"{prefix}x_min"],
        y_min=row[f"{prefix}y_min"],
        x_max=row[f"{prefix}x_max"],
        y_max=row[f"{prefix}y_max"],
    )


def _build_frame(values):
    row = values["row"]
    coordinate_space = None
    visual_asset = None
    if row["image_width"] is not None and row["image_height"] is not None:
        coordinate_space = PixelCoordinateSpace(
            width=row["image_width"],
            height=row["image_height"],
        )
        if row["output_asset_id"] is not None:
            visual_asset = VisualAssetReference(
                asset_id=row["output_asset_id"],
                url=f"/api/assets/{row['output_asset_id']}",
                width=row["image_width"],
                height=row["image_height"],
            )
    return ProcessedFrameResult(
        id=row["id"],
        input_source_id=row["input_source_id"],
        frame_number=row["frame_number"],
        frame_timestamp_seconds=row["frame_timestamp_seconds"],
        image_width=row["image_width"],
        image_height=row["image_height"],
        output_asset_id=row["output_asset_id"],
        visual_asset=visual_asset,
        coordinate_space=coordinate_space,
        processed_at=row["processed_at"],
        detections=values["detections"],
        frame_summaries=values["frame_summaries"],
        grid_cells=[
            GridCellResult.model_validate(cell) for cell in values["grid_cells"]
        ],
        alerts=values["alerts"],
    )


def _validate_pagination(page, page_size):
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise InvalidPaginationError("page must be a positive integer")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= MAX_PAGE_SIZE
    ):
        raise InvalidPaginationError(
            f"page_size must be an integer between 1 and {MAX_PAGE_SIZE}"
        )


def _validate_session_id(session_id):
    if (
        isinstance(session_id, bool)
        or not isinstance(session_id, int)
        or session_id < 1
    ):
        raise InvalidSessionIdError("session_id must be a positive integer")
