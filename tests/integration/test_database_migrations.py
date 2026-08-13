import os
import shutil
import uuid

import pytest
from psycopg import sql

from app.database.connection import open_database_connection
from app.database.migration_runner import (
    MIGRATIONS_DIRECTORY,
    apply_pending_migrations,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL integration tests are not enabled.",
)


@pytest.fixture
def isolated_database_schema():
    schema_name = f"migration_test_{uuid.uuid4().hex}"
    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA {};").format(sql.Identifier(schema_name))
            )

    def connection_factory():
        connection = open_database_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET search_path TO {};").format(sql.Identifier(schema_name))
            )
        return connection

    try:
        yield schema_name, connection_factory
    finally:
        with open_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(
                        sql.Identifier(schema_name)
                    )
                )


def test_fresh_database_applies_migrations_once(isolated_database_schema):
    _schema_name, connection_factory = isolated_database_schema

    first_result = apply_pending_migrations(
        connection_factory=connection_factory,
    )
    second_result = apply_pending_migrations(
        connection_factory=connection_factory,
    )

    assert [migration.version for migration in first_result.applied] == [1, 2]
    assert second_result.applied == ()
    assert [migration.version for migration in second_result.previously_applied] == [
        1,
        2,
    ]

    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version;"
            )
            assert cursor.fetchall() == [
                (1, "create_initial_tables"),
                (2, "add_model_run_profiles"),
            ]
            cursor.execute("SELECT to_regclass('monitoring_sessions');")
            assert cursor.fetchone() == ("monitoring_sessions",)
            cursor.execute("SELECT to_regclass('model_run_profiles');")
            assert cursor.fetchone() == ("model_run_profiles",)


def test_existing_initial_schema_is_adopted_without_data_loss(
    isolated_database_schema,
):
    _schema_name, connection_factory = isolated_database_schema
    initial_sql = (MIGRATIONS_DIRECTORY / "001_create_initial_tables.sql").read_text(
        encoding="utf-8"
    )

    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(initial_sql)
            cursor.execute(
                """
                INSERT INTO monitoring_sessions (session_name, status)
                VALUES (%s, %s)
                RETURNING id;
                """,
                ("legacy session", "completed"),
            )
            session_id = cursor.fetchone()[0]

    result = apply_pending_migrations(connection_factory=connection_factory)

    assert [migration.version for migration in result.applied] == [1, 2]
    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT session_name, status FROM monitoring_sessions WHERE id = %s;",
                (session_id,),
            )
            assert cursor.fetchone() == ("legacy session", "completed")
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version;")
            assert cursor.fetchall() == [(1,), (2,)]


def test_failed_pending_migration_rolls_back_every_change(
    isolated_database_schema,
    tmp_path,
):
    _schema_name, connection_factory = isolated_database_schema
    shutil.copy(
        MIGRATIONS_DIRECTORY / "001_create_initial_tables.sql",
        tmp_path / "001_create_initial_tables.sql",
    )
    (tmp_path / "002_force_failure.sql").write_text(
        "CREATE TABLE migration_should_rollback (id INTEGER); SELECT 1 / 0;",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="division by zero"):
        apply_pending_migrations(
            tmp_path,
            connection_factory=connection_factory,
        )

    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('schema_migrations');")
            assert cursor.fetchone() == (None,)
            cursor.execute("SELECT to_regclass('monitoring_sessions');")
            assert cursor.fetchone() == (None,)
            cursor.execute("SELECT to_regclass('migration_should_rollback');")
            assert cursor.fetchone() == (None,)
