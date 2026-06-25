import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.database.connection import check_database_connection


def main():
    try:
        if check_database_connection():
            print("Database connection successful.")
        else:
            print("Database connection failed.")
            sys.exit(1)
    except Exception as error:
        print(f"Database connection failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
