# How We Develop the Project

We develop the application in small steps, with one GitHub issue for each clear
piece of work. This makes it easier for us to understand what changed, test it,
and connect the implementation history to the thesis.

## Beginning a New Issue

When we begin an issue, we first check that the current work is committed and
that `main` is up to date:

```bash
git status
git switch main
git pull --ff-only
```

We then create a branch that connects the code directly to the issue:

```bash
git switch -c issue-24-grid-based-counting
```

Our usual branch names are:

- `issue-<number>-<short-description>` for issue work;
- `fix/<short-description>` for a defect;
- `docs/<short-description>` for documentation without an existing issue;
- `chore/<short-description>` for tooling or maintenance.

## Local Environment

We keep development tools in the project virtual environment:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
```

When an issue involves PostgreSQL, we use the local `.env` file and start the
database service:

```bash
cp .env.example .env
docker compose up -d postgres
docker compose ps
```

We keep `.env`, downloaded model weights, personal datasets, generated images,
and database data outside Git. Only safe examples and small project samples
belong in the repository.

## How We Approach a Change

We try to keep each change close to the structure described in
`docs/architecture.md`. Image handling, detection, output, and database storage
remain separate because they change for different reasons.

Where possible, we keep ordinary data transformations separate from calls to
YOLO or PostgreSQL. This makes the core logic easier to understand and lets us
test it with small controlled inputs. We add another abstraction only when it
solves a real problem or removes meaningful duplication.

For database work, we use parameterised SQL and keep related writes in one
transaction. For detection work, we record incorrect outputs as well as
successful ones, because completing inference does not prove that the result is
accurate.

## How We Test the Work

We match the amount of testing to the change. A small conversion function usually
needs focused unit tests. Database writes, file output, and complete workflows
need integration tests when they become part of the implemented behavior.

Software tests and model evaluation serve different purposes. Unit tests tell us
whether the application behaves as expected for controlled input. A labelled
evaluation dataset tells us whether the detector is accurate enough for aerial
traffic and crowd monitoring.

Before a pull request, we run:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m compileall app scripts
```

For database changes, we also check the connection and apply the current schema:

```bash
.venv/bin/python scripts/check_db_connection.py
.venv/bin/python scripts/create_database_tables.py
```

When we change the processing pipeline, we run it on a known image and inspect
both the terminal summary and annotated output:

```bash
.venv/bin/python -m app.main
```

## Keeping the Documents Current

We update documentation in the same pull request as the related behavior. The
README follows setup and user-visible commands, the architecture document follows
module responsibilities, and the database document follows stored data. We add
completed milestones and important observations to the development log.

We use **implemented**, **experimental**, and **planned** carefully. This helps us
avoid presenting an unfinished idea or an unverified model result as a completed
part of the application.

## Commits and Pull Requests

Our commit subjects describe the result of a change in a few words:

```text
Add frame-level object count storage
Fix output image write validation
Document the current database schema
```

In a pull request, we connect the branch to its issue and explain what changed,
how we checked it, and what remains limited. Visual changes include an example or
screenshot when that makes the result easier to review.

We keep pull requests small enough to understand in one sitting and merge them
after the relevant checks pass. GitHub Actions repeats the standard checks, but
we still review the behavior and the code ourselves.

## Dependency Updates

Dependabot checks Python packages and GitHub Actions each week. We treat these
pull requests like any other change: CI needs to pass, and we review the effect
before merging. The fact that an update was created automatically is not enough
reason for us to accept it.

## Our Research Record

Alongside the software history, we keep enough information to reproduce formal
thesis experiments. For each experiment, we record:

- the date and commit identifier;
- the model name, source, and version;
- the dataset or input source;
- the confidence threshold and image size;
- preprocessing settings;
- the hardware and software environment;
- accuracy and performance measurements;
- important failure cases.

This record connects the results in the thesis to a specific version of the
application and prevents us from relying on settings that were not documented.
