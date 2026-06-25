import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import open_database_connection


SCHEMA_FILE = (
    PROJECT_ROOT / "app" / "database" / "migrations" / "001_create_initial_tables.sql"
)


def create_database_tables():
    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")

    with open_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema_sql)


def main():
    try:
        create_database_tables()
        print("Initial database tables created successfully.")
    except Exception as error:
        print(f"Failed to create database tables: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
