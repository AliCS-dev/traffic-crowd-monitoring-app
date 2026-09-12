# Backend Container

Issue #77 packages the FastAPI API and detector in one backend image. PostgreSQL
still uses the existing Compose service; the frontend still runs separately.
The complete three-service stack belongs to issue #78.

## Runtime Choice

We use the official PyTorch 2.12.0, CUDA 13.0, cuDNN 9 runtime image, pinned by
SHA-256 digest in the Dockerfile. This matches the PyTorch/CUDA family already
used on the project's RTX 5060 Laptop GPU. The container includes runtime
dependencies, not the project's evaluation and development toolchain.
Application packages live in `/opt/venv`, which reuses the base image's PyTorch
packages through system-site-packages without modifying the system Python.

The base digest fixes the supplied operating-system and PyTorch layers.
`requirements-container.txt` pins the additional Python runtime packages,
including their resolved indirect dependencies. We inspect
`docker run --rm traffic-monitoring-backend:local python -m pip freeze --local`
when reviewing dependency updates, then rebuild and repeat the runtime checks.
Base-image and Torch pins are reviewed together; updates must not silently
replace the supplied CUDA build. System
packages installed through apt still come from the distribution repositories;
this is a reproducible application setup, not a claim of byte-identical builds.
The CUDA libraries make this image much larger than a CPU-only web API image.
We keep the runtime base, without CUDA compiler tools, and leave weights and media
outside the image. We do not publish a container package for this issue.

The [PyTorch release notes](https://pytorch.org/blog/pytorch-2-12-release-blog/)
describe the CUDA 13.0 release configuration. On Windows,
[Docker's GPU support](https://docs.docker.com/desktop/features/gpu/) requires
the WSL2 backend and an appropriate NVIDIA Windows driver. The driver remains
on the host; we do not install an NVIDIA kernel driver in the container.

## Build

From the repository root:

```bash
docker build -t traffic-monitoring-backend:local .
```

The allowlist in `.dockerignore` excludes local environments, Git history,
frontend files, model weights, input/output media, and evaluation datasets.
Only the recorded `dedicated_crowd_counting.json` decision is included from
`data/`, because the API uses it to report unsupported dense-crowd counting.
Database migrations and the small runtime verification script are included.

## Configuration And Storage

```bash
cp .env.backend.example .env.backend
```

We set the database password in this local file to match the PostgreSQL service.
Special characters in a URL password need URL encoding. This file is ignored by
Git and excluded from the image. The example database hostname is `postgres`,
not `localhost`: localhost inside the backend refers to that container itself.

The commands below assume the repository's default Compose network is
`traffic-crowd-monitoring-app_default`. A custom Compose project name changes
that network name; `docker network ls` shows the networks on the local machine.

```bash
docker compose up -d --wait postgres
docker volume create traffic_backend_inputs
docker volume create traffic_backend_outputs
```

The existing runtime checkpoint must be present at
`models/candidates/yolo26m-visdrone/best.pt`. The API verifies its size and SHA-256
against `configs/runtime/yolo26m_visdrone.json`. Mounting `models/` read-only keeps
the checkpoint outside the image and prevents the process from modifying it.

New named input/output volumes inherit the image directory ownership (UID/GID
10001). For existing bind mounts, their permissions must allow that user to write;
we do not make the application root or make every file world-writable to bypass
permissions. The container filesystem contains only disposable caches outside
these persistent volumes.

## Database And Startup

We apply migrations explicitly before starting the API:

```bash
docker run --rm --network traffic-crowd-monitoring-app_default \
  --env-file .env.backend \
  traffic-monitoring-backend:local python scripts/migrate_database.py
```

Then we start one API process with access to GPU 0:

```bash
docker run -d --name traffic-backend \
  --network traffic-crowd-monitoring-app_default \
  --env-file .env.backend --gpus device=0 \
  -p 127.0.0.1:8000:8000 \
  --mount type=bind,src="$PWD/models",dst=/app/models,readonly \
  --mount type=volume,src=traffic_backend_inputs,dst=/app/data/input \
  --mount type=volume,src=traffic_backend_outputs,dst=/app/data/output \
  traffic-monitoring-backend:local
```

Port 8000 must be free; we stop an existing local API or choose a different host
port and update the frontend API address accordingly. We do not start multiple
API processes against the same job queue: the current video worker and interrupted
job recovery are designed for one API process.

```bash
docker inspect traffic-backend --format '{{.State.Health.Status}}'
curl --fail http://localhost:8000/api/health
curl --fail http://localhost:8000/api/ready
docker logs traffic-backend
```

`/api/health` checks the process. `/api/ready`, also used by the Docker healthcheck,
checks the database, checkpoint integrity, and availability of the requested CUDA
device. Readiness does not run an inference on each poll. The explicit smoke
check below verifies that model loading and GPU inference actually work.

## GPU And CPU Checks

```bash
docker exec traffic-backend python scripts/check_backend_runtime.py --require-cuda
```

The script performs one inference on a synthetic image and reports the actual
PyTorch/CUDA versions, selected device, model ID, checksum, and quality-gate status.
Success means the runtime works, not that the detector is accurate.

For a CPU-only development check, the same image can run without `--gpus`, with
`-e API_DEVICE=cpu`. For example, a standalone check without PostgreSQL is:

```bash
docker run --rm -e API_DEVICE=cpu \
  --mount type=bind,src="$PWD/models",dst=/app/models,readonly \
  traffic-monitoring-backend:local python scripts/check_backend_runtime.py
```

CPU inference is slower and this is still the large CUDA-capable image. We do not
maintain a second image or silently fall back from a requested GPU to CPU.
`API_DEVICE` accepts `cpu`, `cuda`, or `cuda:<index>`. It changes only the execution
device; persisted model provenance records the effective device. Model identity,
checksum, class mapping, confidence, image size, and evaluation decision stay intact.

## Image Workflow And Persistence

```bash
curl --fail -X POST http://localhost:8000/api/analyses/images \
  -F image=@data/input/sample_image.jpg \
  -F session_name=container-smoke-image -F grid_rows=2 -F grid_columns=3
```

The response supplies a session ID and result URL. We can open the session from
the frontend or request `/api/analyses/<session-id>` and its returned asset URL.
The image is a development smoke input, not a new detector-quality benchmark.

To recreate the backend, we stop and remove only its container, then repeat the
same startup command and mounts:

```bash
docker stop traffic-backend
docker rm traffic-backend
```

Database and media volumes remain intact. Removing these volumes is a separate,
destructive operation and is not part of normal restart or upgrade instructions.
Known model limitations remain visible: the traffic detector is experimental,
dense-crowd counting is unsupported, and alerts are not verified emergencies.

## Verification Record

On 12 September 2026 we tested the backend with Docker Desktop's WSL2 engine
and the NVIDIA GeForce RTX 5060 Laptop GPU. The container used Python 3.12.3,
PyTorch 2.12.0+cu130, and CUDA runtime 13.0. The image reported by Docker was
`sha256:20f8a918ef2e104f123e595622052df744ed877edb8feffe58bd3966faf27934`;
`docker image inspect` reported 3,379,648,648 bytes (about 3.15 GiB). Actual Docker
disk use also includes shared layers and build cache, so this is not a download
size or total-disk-usage measurement.

We used a separate PostgreSQL container, network, and media volumes for these
checks. The existing thesis database was not used for the container smoke run.

| Check | Observed result |
| --- | --- |
| Dependency consistency | `python -m pip check` passed |
| GPU checkpoint and synthetic inference | Passed on `cuda:0`; checksum matched the tracked profile |
| Explicit CPU fallback | Passed with `API_DEVICE=cpu` and no GPU mount |
| Missing requested GPU | Detector readiness false, database readiness true |
| Database setup | All seven migrations applied inside the image |
| API readiness and Docker health | Ready and healthy |
| Real image upload | Session 1 in the isolated database: 92 detections, six grid cells, one experimental alert |
| Container recreation | Session and original upload persisted; generated image SHA-256 unchanged |
| Image contents and user | UID 10001; no local `.env`, weights, Git history, frontend, or input/output media |
| Python regression suite | 374 tests passed, including PostgreSQL integration tests |

The persisted result image hash was
`fc029d31549468eaf8dc8db750fc01635d96b22feb7af1dbda1985ac523a0363`.
These observations check application operation and persistence; they are not
new detector-quality measurements or final system-performance benchmarks.

CI runs the Python regression suite and Docker's built-in Dockerfile checks.
The real image build, GPU inference, and container-volume checks were performed
locally: ordinary GitHub-hosted CI does not supply this RTX GPU. Complete-stack
automation remains part of issues #78 and #26.
