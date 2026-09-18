from contextlib import contextmanager

from app.database.connection import open_database_connection

# A session lock keeps maintenance separate from every API process, including idle ones.
MEDIA_MAINTENANCE_LOCK = 804_202_601


def acquire_api_lease():
    connection = open_database_connection(connect_timeout=5, autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock_shared(%s)", (MEDIA_MAINTENANCE_LOCK,)
            )
            if not cursor.fetchone()[0]:
                raise RuntimeError(
                    "Media maintenance is active; retry API startup later."
                )
        return connection
    except Exception:
        connection.close()
        raise


@contextmanager
def media_maintenance_snapshot():
    with open_database_connection(connect_timeout=5, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (MEDIA_MAINTENANCE_LOCK,))
            if not cursor.fetchone()[0]:
                raise RuntimeError("Stop every API instance before media cleanup.")
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM video_analysis_jobs "
                "WHERE status IN ('queued', 'processing'))"
            )
            if cursor.fetchone()[0]:
                raise RuntimeError(
                    "Unfinished jobs exist. Recover them through API startup "
                    "before cleanup."
                )
            cursor.execute(
                "SELECT file_path FROM input_sources "
                "UNION SELECT output_file_path FROM processed_frames "
                "WHERE output_file_path IS NOT NULL"
            )
            paths = [row[0] for row in cursor.fetchall()]
        yield paths
