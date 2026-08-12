import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.migrate_database import main, run_database_migrations


def create_database_tables():
    return run_database_migrations()


if __name__ == "__main__":
    main()
