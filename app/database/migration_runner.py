import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.database.connection import open_database_connection

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent / "migrations"
MIGRATION_FILENAME_PATTERN = re.compile(
    r"^(?P<version>\d{3})_(?P<name>[a-z0-9]+(?:_[a-z0-9]+)*)\.sql$"
)
MIGRATION_LOCK_ID = 1_904_202_026


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    filename: str
    checksum: str
    sql: str


@dataclass(frozen=True)
class MigrationResult:
    applied: tuple[Migration, ...]
    previously_applied: tuple[Migration, ...]


def discover_migrations(
    migrations_directory: Path = MIGRATIONS_DIRECTORY,
) -> tuple[Migration, ...]:
    migrations_directory = Path(migrations_directory)
    if not migrations_directory.is_dir():
        raise MigrationError(
            f"Migration directory does not exist: {migrations_directory}"
        )

    migration_files = sorted(migrations_directory.glob("*.sql"))
    if not migration_files:
        raise MigrationError(f"No SQL migration files found in {migrations_directory}.")

    migrations = []
    versions = set()
    for migration_file in migration_files:
        match = MIGRATION_FILENAME_PATTERN.fullmatch(migration_file.name)
        if match is None:
            raise MigrationError(
                "Invalid migration filename "
                f"'{migration_file.name}'. Expected NNN_lowercase_name.sql."
            )

        version = int(match.group("version"))
        if version < 1:
            raise MigrationError(
                "Invalid migration filename "
                f"'{migration_file.name}'. Version must be greater than zero."
            )
        if version in versions:
            raise MigrationError(f"Duplicate migration version: {version:03d}.")

        sql_bytes = migration_file.read_bytes()
        if not sql_bytes.strip():
            raise MigrationError(f"Migration file is empty: {migration_file.name}.")

        try:
            sql = sql_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise MigrationError(
                f"Migration file is not valid UTF-8: {migration_file.name}."
            ) from error

        versions.add(version)
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                filename=migration_file.name,
                checksum=hashlib.sha256(sql_bytes).hexdigest(),
                sql=sql,
            )
        )

    return tuple(sorted(migrations, key=lambda migration: migration.version))


def apply_pending_migrations(
    migrations_directory: Path = MIGRATIONS_DIRECTORY,
    *,
    connection_factory: Callable | None = None,
) -> MigrationResult:
    migrations = discover_migrations(migrations_directory)
    connection_factory = connection_factory or open_database_connection

    with connection_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s);", (MIGRATION_LOCK_ID,))
            _create_migration_history_table(cursor)
            applied_records = _load_applied_migrations(cursor)
            _validate_applied_migrations(migrations, applied_records)

            pending = [
                migration
                for migration in migrations
                if migration.version not in applied_records
            ]
            for migration in pending:
                cursor.execute(migration.sql)
                cursor.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum)
                    VALUES (%s, %s, %s);
                    """,
                    (migration.version, migration.name, migration.checksum),
                )

    previously_applied = tuple(
        migration for migration in migrations if migration.version in applied_records
    )
    return MigrationResult(
        applied=tuple(pending),
        previously_applied=previously_applied,
    )


def _create_migration_history_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY CHECK (version > 0),
            name VARCHAR(255) NOT NULL,
            checksum CHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _load_applied_migrations(cursor) -> dict[int, tuple[str, str]]:
    cursor.execute(
        """
        SELECT version, name, checksum
        FROM schema_migrations
        ORDER BY version;
        """
    )
    return {version: (name, checksum) for version, name, checksum in cursor.fetchall()}


def _validate_applied_migrations(
    migrations: tuple[Migration, ...],
    applied_records: dict[int, tuple[str, str]],
) -> None:
    migrations_by_version = {migration.version: migration for migration in migrations}
    missing_files = sorted(set(applied_records) - set(migrations_by_version))
    if missing_files:
        formatted_versions = ", ".join(f"{version:03d}" for version in missing_files)
        raise MigrationError(
            "Applied migration files are missing from the repository: "
            f"{formatted_versions}."
        )

    for version, (recorded_name, recorded_checksum) in applied_records.items():
        migration = migrations_by_version[version]
        if recorded_name != migration.name:
            raise MigrationError(
                f"Applied migration {version:03d} has a different name."
            )
        if recorded_checksum != migration.checksum:
            raise MigrationError(f"Applied migration {version:03d} has been modified.")
