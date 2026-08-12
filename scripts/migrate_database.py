import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.migration_runner import apply_pending_migrations


def run_database_migrations():
    return apply_pending_migrations()


def main():
    try:
        result = run_database_migrations()
    except Exception as error:
        print(f"Database migration failed: {error}")
        sys.exit(1)

    if result.applied:
        print("Applied database migrations:")
        for migration in result.applied:
            print(f"  {migration.version:03d} {migration.name}")
    else:
        print("Database schema is already up to date.")


if __name__ == "__main__":
    main()
