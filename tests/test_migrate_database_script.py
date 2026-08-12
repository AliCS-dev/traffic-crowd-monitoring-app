from types import SimpleNamespace

import pytest

import scripts.migrate_database as migrate_database
from app.database.migration_runner import MigrationResult


def migration(version, name):
    return SimpleNamespace(version=version, name=name)


def test_migration_script_prints_applied_versions(monkeypatch, capsys):
    monkeypatch.setattr(
        migrate_database,
        "run_database_migrations",
        lambda: MigrationResult(
            applied=(migration(1, "create_initial_tables"),),
            previously_applied=(),
        ),
    )

    migrate_database.main()

    assert capsys.readouterr().out == (
        "Applied database migrations:\n  001 create_initial_tables\n"
    )


def test_migration_script_reports_up_to_date_database(monkeypatch, capsys):
    monkeypatch.setattr(
        migrate_database,
        "run_database_migrations",
        lambda: MigrationResult(
            applied=(),
            previously_applied=(migration(1, "create_initial_tables"),),
        ),
    )

    migrate_database.main()

    assert capsys.readouterr().out == "Database schema is already up to date.\n"


def test_migration_script_reports_failure(monkeypatch, capsys):
    def fail():
        raise RuntimeError("test failure")

    monkeypatch.setattr(migrate_database, "run_database_migrations", fail)

    with pytest.raises(SystemExit) as error:
        migrate_database.main()

    assert error.value.code == 1
    assert capsys.readouterr().out == "Database migration failed: test failure\n"
