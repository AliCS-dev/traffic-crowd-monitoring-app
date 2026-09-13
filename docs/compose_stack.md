# Full Application with Docker Compose

We run the browser application, API, and PostgreSQL as separate services. Nginx
serves the compiled React application and forwards `/api/` requests to FastAPI.
Only Nginx is published, on localhost port 8080. The backend and database remain
on the Compose network.

```text
Browser :8080 -> frontend (Nginx) -> backend :8000 -> postgres :5432
                                      |
                                      +-> read-only models, uploads, outputs
```

The existing `docker-compose.yml` is still the database-only development setup.
`docker-compose.app.yml` is the complete CPU stack; `docker-compose.gpu.yml`
adds NVIDIA access to the backend only. We keep these entry points separate so
existing local Python experiments and their database are unaffected.

## First Start

From the repository root, we need Docker Compose v2, the runtime weights, and a
local `.env`. Docker Desktop on Windows needs WSL2 integration enabled for this
distribution. GPU execution also needs the host NVIDIA driver and Docker GPU
support; the [backend guide](backend_container.md) explains these prerequisites.

If `.env` does not already exist, we create it from `.env.example` and choose a
local password. We do not overwrite an existing configuration:

```bash
cp -n .env.example .env
```

The selected checkpoint must already be at
`models/candidates/yolo26m-visdrone/best.pt`, readable by container UID 10001.
The repository's `scripts/preflight_model_candidates.py --download` command can
download and verify the recorded candidates when using the local Python setup.
The container never downloads alternative weights silently. A missing or changed
checkpoint fails backend readiness.

For the RTX setup, one command builds and starts the application:

```bash
docker compose -f docker-compose.app.yml -f docker-compose.gpu.yml up -d --build --wait --wait-timeout 240
```

The browser address is <http://localhost:8080>. `FRONTEND_PORT` in `.env` changes
the host port if it is occupied. We use one API process and one video worker;
this is a local thesis demonstration, not a multi-user hosting deployment.

For CPU-only development, we omit the GPU override:

```bash
docker compose -f docker-compose.app.yml up -d --build --wait --wait-timeout 240
```

This uses the same backend image with `API_DEVICE=cpu`, so it still includes the
CUDA libraries but does not request a GPU. Switching modes recreates the backend;
we finish active analyses first. GPU mode exposes `GPU_DEVICE_ID` (default 0)
from the host as `cuda:0` inside the backend. It is an explicit mode, not automatic
fallback. The migration and frontend services do not receive GPU access.

## Configuration and Startup

We reuse `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` from `.env`.
Inside the backend, `DATABASE_URL=postgresql://` uses Psycopg/libpq's `PGHOST`,
`PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD` values. This avoids constructing
a URL from unescaped credentials. The local Python `DATABASE_URL` and
`POSTGRES_PORT` do not control container networking. We do not print resolved
Compose configuration into logs because it contains environment credentials.

The frontend image contains no environment file. Its explicit empty
`VITE_API_BASE_URL` makes API and result-image URLs same-origin. Local Vite
development retains its default `http://localhost:8000` backend. No browser CORS
edit is needed for the container setup.

Startup follows dependency state, not fixed delays:

1. PostgreSQL passes `pg_isready`.
2. The short-lived `migrate` service applies pending ordered migrations.
3. The backend starts and passes database/checkpoint/device readiness.
4. Nginx starts and passes its own `/healthz` probe.

An exited migration container with code 0 is expected. A failed migration blocks
backend startup. Existing migrations are not reapplied. The frontend health probe
checks Nginx itself; `/api/ready` checks the backend dependencies. A database or
backend outage is therefore distinguishable from an unavailable web server.
Compose health conditions gate startup, not continuous dependency restarts.

Nginx caps complete requests at 512 MiB, leaving multipart overhead above the
default 500 MiB video limit. The API still enforces its lower per-media byte and
image-dimension limits. Raising uploads beyond this proxy ceiling also requires
an explicit `nginx.conf` change and rebuild. Nginx streams requests rather than
buffering a second full upload. The proxy waits up to 300 seconds between response reads
for synchronous image inference. Asynchronous video processing uses short status
requests. A timed-out browser request does not cancel already accepted work.
Docker DNS re-resolution lets the proxy follow a recreated backend container.

## Storage and Daily Use

The default full-stack project name is `traffic-monitoring-app`. Its volumes are
`traffic-monitoring-app_postgres_data`, `traffic-monitoring-app_uploads`, and
`traffic-monitoring-app_outputs`. These are separate from the old development
database and from host `data/input` and `data/output` folders. An initially empty
session history is expected; we do not copy old sessions automatically.

We keep the same file arguments for subsequent GPU commands:

```bash
docker compose -f docker-compose.app.yml -f docker-compose.gpu.yml ps -a
docker compose -f docker-compose.app.yml -f docker-compose.gpu.yml logs --tail 80 backend migrate
curl --fail http://localhost:8080/healthz
curl --fail http://localhost:8080/api/ready
docker compose -f docker-compose.app.yml -f docker-compose.gpu.yml exec postgres psql -U traffic_user -d traffic_monitoring
docker compose -f docker-compose.app.yml -f docker-compose.gpu.yml down
```

The `psql` command assumes the example database/user names. `down` removes the
containers and network, not named volumes. We avoid `down -v` because it deletes
the stack's database and media. Changing the project name selects different
volumes. Changing a password in `.env` does not change a role already stored in
PostgreSQL's volume. Database and media backups must be kept together.

The frontend runs as UID 101; the backend runs as UID 10001. Neither image embeds
credentials or model weights. Images stay local rather than being published to
a registry. This setup has no authentication or TLS and stays localhost-only.
GitHub reported open Pillow and PyTorch advisories in the inherited backend
runtime on 13 September 2026. Their updates and compatibility checks are tracked
under #80, including Dependabot PRs #104 and #105. Until that review is complete,
we use trusted local media only and do not expose this demonstration publicly.

## Live Browser Check

The dedicated check runs against an already healthy stack, with no API mocks.
It creates one stored image session for each desktop/mobile test. We use an
isolated Compose project for verification rather than a thesis evidence database.
From `frontend/`, with Node 24 and a local image:

```bash
npm ci
npx playwright install --with-deps chromium
STACK_IMAGE=/absolute/path/to/image.jpg npm run test:stack
```

`STACK_BASE_URL` can select another localhost port. For CPU mode we also set
`STACK_EXPECTED_DEVICE=cpu`. To check persistence after container recreation,
we can reuse a session and the image hash printed by a previous run:

```bash
STACK_SESSION_ID=1 STACK_EXPECTED_ASSET_SHA256=<recorded-hash> npm run test:stack
```

The check saves screenshots and a JSON evidence attachment in the ignored
`frontend/test-results/` directory. CI validates both Compose variants, builds
the frontend image, and checks Nginx/SPA routing, alongside existing unit,
database, and mocked browser tests. The real GPU workflow is a local check;
it is not presented as a GitHub-hosted GPU test or an accuracy benchmark.

## Verification Record

On 13 September 2026 we used the isolated `traffic-stack-check` project on
Docker Desktop/WSL2 with the RTX 5060 Laptop GPU. No existing thesis database was
used for these container checks. The frontend used Nginx 1.30.4 as UID 101 and
the unchanged backend used PyTorch 2.12.0+cu130 as UID 10001.

| Check | Observed result |
| --- | --- |
| Fresh database startup | All seven migrations applied before API readiness |
| GPU startup | All three long-running services healthy; only localhost:8080 published |
| GPU isolation | Only the backend had an NVIDIA device reservation |
| Desktop and mobile browser submission | Passed at 1440x1000 and 320x900; no mocked API responses |
| Each sample-image result | 92 detections, six grid cells; count-summary total matched detections |
| Browser rendering | Saved image decoded, grid visible, no horizontal page overflow or page errors |
| Same-origin requests | API requests and saved asset URLs stayed on the frontend origin |
| Full stack down/up | Original uploads, session records, and byte-identical output persisted |
| Repeated migrations | Existing schema reported up to date |
| CPU-only Compose | Healthy without a GPU reservation; synthetic inference passed with CUDA unavailable |
| Database outage | Proxy readiness returned 503 with database not ready; frontend health stayed 200 |
| Backend outage | Proxy returned 502; frontend health stayed 200 |
| Regression tests | 374 Python tests including PostgreSQL integration; 103 frontend unit tests; eight existing browser checks passed |
| Configuration checks | Both Compose variants valid; frontend Dockerfile and Nginx validation passed |

The sample image came from the existing local `data/input/sample_image.jpg`.
The persisted output SHA-256 was
`fc029d31549468eaf8dc8db750fc01635d96b22feb7af1dbda1985ac523a0363`.
Both original uploads retained SHA-256
`e494a93fde70cb0ee76442233499b4cc162219715336d5461cd0ca4ca81f7b4d`.
Desktop and mobile retrieval checks passed again after full container recreation.
These checks verify deployment and persistence, not detection accuracy or a
system-performance budget. The failed detector quality gate and unsupported
dense-crowd decision remained unchanged and visible.

Docker reported 28,762,233 bytes (about 27.4 MiB) for the frontend image
`sha256:041cebb145bbb9e9ad510460fa670b6459a7aa1fbc65023a9f091870e3407dad`.
This is Docker's image-size field, not download size or total disk use.
The frontend build context was about 267 kB and excluded local environment
files, dependencies, and browser artifacts. The final image contains the static
build and Nginx rather than the Node builder or source workspace.

## References

Our GPU override follows [Docker's GPU device reservations](https://docs.docker.com/compose/how-tos/gpu-support/).
The reverse proxy uses [Nginx upstream DNS resolution](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server).
