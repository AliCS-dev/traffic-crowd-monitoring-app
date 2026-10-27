# Application Diagrams

[Architecture guide](../architecture.md) | [Documentation index](../README.md)

We keep the diagrams as Graphviz text files and render PNG and SVG versions.
The README uses the application diagram; the architecture guide also shows
the Docker build and startup sequence. The PNGs display directly on GitHub.
The SVGs remain readable when enlarged or used as a basis for thesis figures.

| Diagram | Files | Source of the details |
| --- | --- | --- |
| Running application | [PNG](application_architecture.png), [SVG](application_architecture.svg), [DOT](application_architecture.dot) | Compose services, API routes, processing services and database repositories |
| Docker build and startup | [PNG](docker_lifecycle.png), [SVG](docker_lifecycle.svg), [DOT](docker_lifecycle.dot) | Dockerfiles, Compose dependency conditions and healthchecks |
| Database ER diagram | [PNG](../database/database_schema.png), [SVG](../database/database_schema.svg), [DOT](../database/database_schema.dot) | Migrations 001-009, the migration runner and PostgreSQL schema metadata |

## What the Figures Describe

The application figures describe `docker-compose.app.yml` with the optional
GPU override. The database-only `docker-compose.yml` is a different development
entry point. We do not combine the two deployments in one figure.

Solid lines in the application diagram show calls or storage access. Dashed
lines show configuration, hardware access or startup work. The browser is
outside Docker, and the processing components share one backend container.
Named volumes are storage mounts, not services on the internal network.

The ER diagram uses crow's-foot notation rather than processing arrows. Its
column names, types and nullability were checked against PostgreSQL on 26 October
2026 and compared with the migrations. It includes schema metadata only,
not user records or credentials. Foreign keys and unique keys describe allowed
relationships, not the number of rows currently in the database.

We checked the application figures against:

- [Full-stack Compose](../../docker-compose.app.yml) and [GPU override](../../docker-compose.gpu.yml).
- [Backend Dockerfile](../../Dockerfile), [frontend Dockerfile](../../frontend/Dockerfile) and [Nginx configuration](../../frontend/nginx.conf).
- [API dependencies](../../app/api/dependencies.py), [image analysis](../../app/services/image_analysis_service.py) and [video analysis](../../app/services/video_analysis_service.py).
- [Database migrations](../../app/database/migrations) and [migration runner](../../app/database/migration_runner.py).

## Updating the Images

After changing the relevant source, edit the `.dot` file and render both image
formats. With Graphviz installed, run these commands from the repository root:

```bash
dot -Tpng -Gdpi=150 docs/diagrams/application_architecture.dot -o docs/diagrams/application_architecture.png
dot -Tsvg docs/diagrams/application_architecture.dot -o docs/diagrams/application_architecture.svg
dot -Tpng -Gdpi=150 docs/diagrams/docker_lifecycle.dot -o docs/diagrams/docker_lifecycle.png
dot -Tsvg docs/diagrams/docker_lifecycle.dot -o docs/diagrams/docker_lifecycle.svg
dot -Tpng -Gdpi=150 docs/database/database_schema.dot -o docs/database/database_schema.png
dot -Tsvg docs/database/database_schema.dot -o docs/database/database_schema.svg
```

These versions use Graphviz 2.43.0 and DejaVu Sans. Check the images after
rendering: labels must remain readable and connections must not pass through
table text. Keep the source and generated images in the same change. No image
generation model or external diagram service is needed, and rendering does not
connect to the application or modify the database.
