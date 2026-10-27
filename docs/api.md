# HTTP API

[Documentation index](README.md) | [Local setup](local_development.md)

We use the API for browser uploads, background video jobs and stored results.
These examples use a separately running API on port 8000. With the Compose
application, use `http://localhost:8080` instead. Replace angle-bracket IDs with
values returned by your own requests.

## Running the API

The FastAPI backend is a separate entry point from the existing image CLI. We
start it locally with:

```bash
.venv/bin/uvicorn app.api.application:app \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

The API provides these routes:

- `GET /api/health` confirms that the HTTP process can respond;
- `GET /api/ready` checks PostgreSQL and verifies the configured checkpoint;
- `GET /api/capabilities` returns public upload formats and option limits;
- `GET /api/analyses` returns paginated monitoring-session history;
- `POST /api/analyses/images` validates, processes, and stores one image;
- `POST /api/analyses/videos` validates and queues one video;
- `GET /api/analyses/videos/{session_id}` returns video-job progress;
- `GET /api/analyses/{session_id}` returns one complete stored result;
- `GET /api/assets/{asset_id}` returns one controlled generated image;
- `GET /api/assets/{asset_id}/source` returns its unannotated processed image, when recorded;
- `GET /docs` opens the generated interactive OpenAPI documentation;
- `GET /openapi.json` returns the machine-readable API contract.

Readiness returns HTTP `503` when a dependency is unavailable. Detector
readiness means that the configured checkpoint exists, matches its recorded
identity, and that a requested CUDA device is available. It does not change the
failed model quality-gate result or claim that
the detector is accurate enough for operational monitoring.

The detector is loaded only when the first analysis request needs it. Starting
the server, checking health, and generating documentation therefore do not
allocate GPU model memory. PostgreSQL remains the only service in the default
development Compose file. The backend can also run in its own GPU-enabled container; its
build, storage, health, CPU fallback, and verification commands are in
[Backend Container](backend_container.md). The frontend container and
combined stack are described in [Full Application Compose](compose_stack.md).

Development browser origins are configured as a comma-separated list in
`.env`:

```text
API_CORS_ORIGINS=http://localhost:5173
API_MAX_IMAGE_UPLOAD_MB=10
API_MAX_IMAGE_PIXELS=40000000
API_MAX_GRID_DIMENSION=20
API_MAX_VIDEO_UPLOAD_MB=500
API_VIDEO_WORKERS=1
```

Wildcard CORS and non-positive upload limits are rejected. The image endpoint
accepts JPG, JPEG, and PNG only. It checks the extension, MIME type, encoded byte
size, actual image format, decoded dimensions, and OpenCV decoding before
inference. Uploaded paths are never trusted as storage paths.

With PostgreSQL running and migrations applied, we can submit a controlled image
analysis from the terminal:

```bash
curl -X POST http://127.0.0.1:8000/api/analyses/images \
  -F "image=@data/input/sample_image.jpg;type=image/jpeg" \
  -F "session_name=sample API image" \
  -F "grid_rows=3" \
  -F "grid_columns=4"
```

The response contains the database session ID and a result URL. The request uses
the tracked runtime model profile; it does not accept ad hoc confidence, image
size, class-mapping, or checkpoint overrides. It also includes a
`dense_crowd_analysis` object. Its current status is `unsupported`, its `count`
is null, and it links to the evaluation that rejected the tested P2PNet
checkpoint. Detector-based person summaries remain ordinary object detections;
they are not presented as a dedicated dense-crowd estimate. A completed result
can then be read with:

```bash
curl http://127.0.0.1:8000/api/analyses/<session-id>
```

Videos use the same stored-result URL but are queued first:

```bash
curl -X POST http://127.0.0.1:8000/api/analyses/videos \
  -F "video=@data/input/example.mp4;type=video/mp4" \
  -F "session_name=sample API video" \
  -F "sampling_interval_seconds=1" \
  -F "grid_rows=3" \
  -F "grid_columns=4"

curl http://127.0.0.1:8000/api/analyses/videos/<session-id>
```

The create request returns HTTP `202` after validation, upload storage, and the
queued database record are complete. The progress route reports `queued`,
`processing`, `completed`, or `failed`. Once completed, the normal result route
returns ordered frames, detections, summaries, optional grids, and a visual asset
reference for each sampled frame. It also returns any experimental threshold
notifications generated from those stored counts.

Successful uploads and generated images use UUID filenames under ignored data
directories. Image outputs are stored in `data/output/analyses/`, while sampled
video-frame outputs are stored in `data/output/video-frames/`. The result JSON
contains a URL such as `/api/assets/<asset-id>` and never exposes the private
server path. We can download that generated JPEG with:

```bash
curl http://127.0.0.1:8000/api/assets/<asset-id> --output result.jpg
```

New image analyses and sampled video frames also include `source_asset`, with
the same UUID, a `/source` URL and an empty `rendered_overlays` list. Its pixels
have the same processed dimensions as the stored box and grid coordinates.
`visual_asset` remains the annotated download. Older frames have a null
`source_asset`; we do not reconstruct their media or rerun inference during a
read. Both asset routes use the same stored-path checks and allowed directories.

All visual coordinates use the processed image returned by that URL. The origin
is the top-left corner, x increases to the right, and y increases downwards. The
annotated JPEG already contains detection boxes; the source JPEG does not.
Detection records and grid cells remain in the JSON so the browser can draw
interactive layers over the clean image without changing either saved file.
