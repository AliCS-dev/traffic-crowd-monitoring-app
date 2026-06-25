# Development Workflow

This project is developed incrementally. Each GitHub issue should be implemented on a separate branch and kept focused on one clear change.

## Local Checks

Install development dependencies:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
```

Run these checks before opening a pull request:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m compileall app scripts
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

## Database Check

For work that depends on PostgreSQL:

```bash
docker compose up -d postgres
.venv/bin/python scripts/check_db_connection.py
```

## Branch Naming

Use short branch names that match the work:

```text
issue-19-initial-database-tables
issue-20-store-detection-results
chore/scalable-ci-automation
```

## Pull Requests

Pull requests should describe:

- what changed
- how it was tested
- which issue it closes or supports

Keep pull requests small enough to review in one sitting.
