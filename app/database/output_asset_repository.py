from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from psycopg.rows import dict_row

from app.database.connection import open_database_connection


@dataclass(frozen=True)
class OutputAssetRecord:
    asset_id: UUID
    file_path: Path


def get_output_asset(
    asset_id: UUID,
    *,
    connection_factory: Callable = open_database_connection,
) -> OutputAssetRecord | None:
    with connection_factory() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT output_asset_id, output_file_path
                FROM processed_frames
                WHERE output_asset_id = %s;
                """,
                (asset_id,),
            )
            row = cursor.fetchone()

    if row is None:
        return None
    return OutputAssetRecord(
        asset_id=row["output_asset_id"],
        file_path=Path(row["output_file_path"]),
    )
