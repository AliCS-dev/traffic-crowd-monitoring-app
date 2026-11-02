# Application Diagrams

[Architecture guide](../architecture.md) | [Documentation index](../README.md)

We use two views: an overview of the applications and stores, followed by the
components inside the backend. Their editable sources are Mermaid files. PNG
exports display on GitHub; SVG and PDF exports stay sharp when enlarged.

| Diagram | Files | Source of the details |
| --- | --- | --- |
| Container view with deployment details | [PNG](application_architecture.png), [SVG](application_architecture.svg), [PDF](application_architecture.pdf), [Mermaid](application_architecture.mmd) | Browser client, Nginx, API, database, named volumes and optional GPU |
| Backend component view | [PNG](backend_components.png), [SVG](backend_components.svg), [PDF](backend_components.pdf), [Mermaid](backend_components.mmd) | Routes, image/video orchestration, shared detection and repositories |
| Docker build and startup | [PNG](docker_lifecycle.png), [SVG](docker_lifecycle.svg), [DOT](docker_lifecycle.dot) | Dockerfiles, Compose dependency conditions and healthchecks |
| Database ER diagram | [PNG](../database/database_schema.png), [SVG](../database/database_schema.svg), [DOT](../database/database_schema.dot) | Migrations 001-009, the migration runner and PostgreSQL schema metadata |

## What the Figures Describe

We follow the [C4 container](https://c4model.com/diagrams/container),
[component](https://c4model.com/diagrams/component) and
[notation](https://c4model.com/diagrams/notation) guidance: each view has a scope,
element types, technologies, short responsibilities and a legend. Arrows point
from the caller or access initiator to its dependency, not every return path.

The overview includes deployment annotations, so it is not a pure C4 container
diagram. The React client belongs to our software system but runs outside Docker.
Named volumes are storage resources, not external software systems; the optional
GPU is a host resource, not a network service. Solid arrows represent network
requests, dashed arrows filesystem access, and thick arrows hardware access.

The backend view groups related Python modules within one process. Its internal
solid arrows are Python calls; external solid arrows name network protocols.
The video worker shares the API process. There is no separate broker, distributed
worker or browser-to-database connection. Colour separates routing, processing,
data and hardware roles; labels also identify those roles in monochrome.

We omit helper functions, individual endpoints, model-weight mounts and startup
tasks from these two views. The [architecture text](../architecture.md) explains
those details. Build/startup ordering stays in the existing lifecycle figure.
The lifecycle and ER figures are not redesigned in this change.

The ER diagram uses crow's-foot notation rather than processing arrows. Its
column names, types and nullability were checked against PostgreSQL on 26 October
2026 and compared with the migrations. It includes schema metadata only,
not user records or credentials. Foreign keys and unique keys describe allowed
relationships, not the number of rows currently in the database.

## Connection to the Code

| Diagram group | Implementation |
| --- | --- |
| Browser client | [Frontend source](../../frontend/src) |
| Web server and proxy | [Nginx configuration](../../frontend/nginx.conf) |
| API router layer | [Routes](../../app/api/routes), [dependencies](../../app/api/dependencies.py), [asset service](../../app/services/output_asset_service.py) |
| Image analysis | [Orchestration](../../app/services/image_analysis_service.py), [upload validation](../../app/services/image_upload_service.py) |
| Video analysis | [Job orchestration](../../app/services/video_analysis_service.py), [frame sampling](../../app/services/frame_sampling_service.py) |
| Shared detection | [Detector](../../app/services/detection_service.py), [preprocessing](../../app/services/preprocessing_service.py), [video frame processing](../../app/services/video_detection_service.py) |
| Repository layer | [Database package](../../app/database) |

The arrows show responsibilities rather than every intermediate call. Result
routes use application dependencies, and asset routes delegate to the asset
service; the router itself does not execute SQL. Shared detection returns boxes
and class information, not a verified crowd-density estimate. The failed model
gate and unsupported dense-crowd result are unchanged.

Deployment details were checked against:

- [Full-stack Compose](../../docker-compose.app.yml) and [GPU override](../../docker-compose.gpu.yml).
- [Backend Dockerfile](../../Dockerfile), [frontend Dockerfile](../../frontend/Dockerfile) and [Nginx configuration](../../frontend/nginx.conf).
- [API dependencies](../../app/api/dependencies.py), [image analysis](../../app/services/image_analysis_service.py) and [video analysis](../../app/services/video_analysis_service.py).
- [Database migrations](../../app/database/migrations) and [migration runner](../../app/database/migration_runner.py).

## Rendering the Mermaid Sources

The exports use Mermaid CLI **12.0.0**, Mermaid **12.2.0**, the ELK layout and the
shared [rendering configuration](mermaid-config.json). These are documentation
tools, not application dependencies. We can install them outside the repository:

```bash
npm install --prefix /tmp/thesis-mermaid @mermaid-js/mermaid-cli@12.0.0 mermaid@12.2.0
```

With Node available, these commands regenerate all six exports from the repository
root. The CLI uses Chromium through Puppeteer and fits each PDF to its figure.

```bash
for diagram in application_architecture backend_components; do
  for format in png svg pdf; do
    /tmp/thesis-mermaid/node_modules/.bin/mmdc \
      --configFile docs/diagrams/mermaid-config.json \
      --input "docs/diagrams/$diagram.mmd" \
      --output "docs/diagrams/$diagram.$format" \
      --size 1800 --backgroundColor white
  done
done
```

An existing Chromium installation can be selected with `--puppeteerConfigFile`.
Browser-library requirements depend on the environment. The diagram sources
contain no remote image, icon or font references. Other Mermaid versions or
renderers may choose different layouts, so the generated exports are the reviewed
figures. We keep the sources, configuration and exports together when updating
them. Rendering does not connect to the application or modify the database.

The separate lifecycle and ER figures still use Graphviz:

```bash
dot -Tpng -Gdpi=150 docs/diagrams/docker_lifecycle.dot -o docs/diagrams/docker_lifecycle.png
dot -Tsvg docs/diagrams/docker_lifecycle.dot -o docs/diagrams/docker_lifecycle.svg
dot -Tpng -Gdpi=150 docs/database/database_schema.dot -o docs/database/database_schema.png
dot -Tsvg docs/database/database_schema.dot -o docs/database/database_schema.svg
```

Their existing exports use Graphviz 2.43.0 and DejaVu Sans.

## Thesis and Defence

We use the overview to introduce the application and the backend view to explain
processing and persistence. The surrounding text covers reasons and trade-offs.
Each figure needs its own page or slide, with a readable font size rather than
being squeezed beside a paragraph. The exported figures use a top-down layout.

The existing LaTeX project can include the PDF exports with `graphicx`:

```latex
\begin{figure}[htbp]
  \centering
  \includegraphics[width=\linewidth]{figures/architecture/application_architecture.pdf}
  \caption{Container view with deployment details of the traffic and crowd monitoring application.}
  \label{fig:application-containers}
\end{figure}
```

The second file is `backend_components.pdf`, with a caption such as "Backend
components and their dependencies within the application API." These exports
are available here; the separate LaTeX project has not been edited or compiled.
