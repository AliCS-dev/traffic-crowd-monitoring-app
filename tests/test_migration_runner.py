from pathlib import Path

import pytest

from app.database.migration_runner import (
    MigrationError,
    apply_pending_migrations,
    discover_migrations,
)


def write_migration(directory: Path, filename: str, sql: str) -> None:
    (directory / filename).write_text(sql, encoding="utf-8")


class FakeCursor:
    def __init__(self, applied_records=()):
        self.applied_records = list(applied_records)
        self.execute_calls = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, parameters=None):
        normalized_query = " ".join(query.split())
        self.execute_calls.append((normalized_query, parameters))
        if normalized_query.startswith("SELECT version, name, checksum"):
            self._rows = list(self.applied_records)

    def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.exit_exception_type = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_exception_type = exc_type
        return False

    def cursor(self):
        return self._cursor


def test_discover_migrations_returns_numerical_order_and_checksums(tmp_path):
    write_migration(tmp_path, "010_add_index.sql", "SELECT 10;")
    write_migration(tmp_path, "002_add_status.sql", "SELECT 2;")
    write_migration(tmp_path, "001_create_tables.sql", "SELECT 1;")
    (tmp_path / "README.md").write_text("Migration notes.", encoding="utf-8")

    migrations = discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == [1, 2, 10]
    assert [migration.name for migration in migrations] == [
        "create_tables",
        "add_status",
        "add_index",
    ]
    assert all(len(migration.checksum) == 64 for migration in migrations)


@pytest.mark.parametrize(
    "filename",
    [
        "1_missing_padding.sql",
        "001-uses-hyphens.sql",
        "001_Uppercase.sql",
        "000_zero_version.sql",
    ],
)
def test_discover_migrations_rejects_invalid_sql_filenames(tmp_path, filename):
    write_migration(tmp_path, filename, "SELECT 1;")

    with pytest.raises(MigrationError, match="Invalid migration filename"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_duplicate_versions(tmp_path):
    write_migration(tmp_path, "001_create_tables.sql", "SELECT 1;")
    write_migration(tmp_path, "001_other_name.sql", "SELECT 2;")

    with pytest.raises(MigrationError, match="Duplicate migration version: 001"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_empty_directory(tmp_path):
    with pytest.raises(MigrationError, match="No SQL migration files"):
        discover_migrations(tmp_path)


def test_apply_pending_migrations_executes_and_records_each_file(tmp_path):
    write_migration(tmp_path, "001_create_tables.sql", "SELECT 1;")
    write_migration(tmp_path, "002_add_status.sql", "SELECT 2;")
    cursor = FakeCursor()
    connection = FakeConnection(cursor)

    result = apply_pending_migrations(
        tmp_path,
        connection_factory=lambda: connection,
    )

    assert [migration.version for migration in result.applied] == [1, 2]
    assert result.previously_applied == ()
    executed_sql = [query for query, _parameters in cursor.execute_calls]
    assert executed_sql.index("SELECT 1;") < executed_sql.index("SELECT 2;")
    history_inserts = [
        parameters
        for query, parameters in cursor.execute_calls
        if query.startswith("INSERT INTO schema_migrations")
    ]
    assert [parameters[:2] for parameters in history_inserts] == [
        (1, "create_tables"),
        (2, "add_status"),
    ]
    assert connection.exit_exception_type is None


def test_apply_pending_migrations_skips_verified_history(tmp_path):
    write_migration(tmp_path, "001_create_tables.sql", "SELECT 1;")
    migration = discover_migrations(tmp_path)[0]
    cursor = FakeCursor(
        applied_records=[(migration.version, migration.name, migration.checksum)]
    )

    result = apply_pending_migrations(
        tmp_path,
        connection_factory=lambda: FakeConnection(cursor),
    )

    assert result.applied == ()
    assert result.previously_applied == (migration,)
    assert not any(query == "SELECT 1;" for query, _ in cursor.execute_calls)


@pytest.mark.parametrize(
    ("recorded_name", "recorded_checksum", "message"),
    [
        ("different_name", None, "different name"),
        (None, "0" * 64, "has been modified"),
    ],
)
def test_apply_pending_migrations_rejects_changed_history(
    tmp_path,
    recorded_name,
    recorded_checksum,
    message,
):
    write_migration(tmp_path, "001_create_tables.sql", "SELECT 1;")
    migration = discover_migrations(tmp_path)[0]
    cursor = FakeCursor(
        applied_records=[
            (
                migration.version,
                recorded_name or migration.name,
                recorded_checksum or migration.checksum,
            )
        ]
    )

    with pytest.raises(MigrationError, match=message):
        apply_pending_migrations(
            tmp_path,
            connection_factory=lambda: FakeConnection(cursor),
        )


def test_apply_pending_migrations_rejects_missing_applied_file(tmp_path):
    write_migration(tmp_path, "001_create_tables.sql", "SELECT 1;")
    cursor = FakeCursor(applied_records=[(2, "removed_migration", "0" * 64)])

    with pytest.raises(MigrationError, match="missing from the repository: 002"):
        apply_pending_migrations(
            tmp_path,
            connection_factory=lambda: FakeConnection(cursor),
        )
