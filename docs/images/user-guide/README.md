# User Guide Screenshots

[User guide](../../user_guide.md) | [Documentation index](../../README.md)

We captured these screenshots on 27 October 2026 from the running application,
using its real API, PostgreSQL database and GPU detector. No API responses,
detections or counts were substituted. They illustrate application behaviour,
not detection accuracy or a new evaluation result.

## What We Captured

| File | What it shows |
| --- | --- |
| `workspace.png` | Image selected, session named and a two-row, three-column grid configured |
| `image-result.png` | Clean scene with interactive boxes, grid selection and the failed-quality warning |
| `image-result-mobile.png` | The same analysis with the inspector below the scene at 390 pixels wide |
| `model-status.png` | The unsupported crowd decision and model settings; a browser screenshot of this page section |
| `session-history.png` | The completed image session available to reopen |

The desktop browser viewport was 1440 by 1000 pixels. The model-status image
captures only the relevant section. The mobile figure is a full-page capture
at 390 pixels wide.
No application elements were hidden or rewritten for the screenshots.

The capture used the working `issue-116-analysis-workspace` build and the
`yolo26m-visdrone` model on `cuda:0`. The build records a modified source state,
not a clean release commit. Session 4 belongs to the isolated
`traffic-issue116` database, not the normal development database. It contains
27 predicted objects and six grid cells. Those counts are not reference labels.
The [capture record](capture.json) includes the input, checkpoint, backend-source,
annotated-image, clean-image, frontend-entry and screenshot hashes.

## Media Attribution

The input is `data/runtime-regression/fixtures/roundabout_6.png`, from
*Traffic images captured from UAVs*, version 1, by **Sergio Ghisler,
Javier Sanchez-Soriano and Sergio Bemposta Rosende**.
The [source record](https://zenodo.org/records/5776219) identifies the licence
as [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The repository's
[fixture record](../../../data/runtime-regression/README.md) documents the
source and the licence check.

The input file is unchanged. The application resizes it for processing and the
browser draws predicted boxes and an interactive grid over the clean pixels.
The image-result screenshot includes those modifications. We distribute the media
derivative under CC BY 4.0 with this attribution; no endorsement is implied.
This is a low, oblique roundabout view, not evidence of performance on high,
top-down aerial scenes. It was already a development fixture, not a new holdout.

## Repeating the Capture

The [capture script](../../../frontend/scripts/capture-docs.mjs) submits one
image and overwrites these five screenshots and `capture.json`. Use a separate
local demonstration database, not a frozen evaluation database. From the
repository root, after the [Compose prerequisites](../../compose_stack.md#first-start):

```bash
FRONTEND_PORT=8081 BACKEND_IMAGE=traffic-monitoring-backend:docs \
  docker compose -p traffic-docs -f docker-compose.app.yml -f docker-compose.gpu.yml \
  up -d --build --wait --wait-timeout 240

cd frontend
npm ci
npx playwright install --with-deps chromium
DOCS_BASE_URL=http://localhost:8081 node scripts/capture-docs.mjs
```

The script prints the created session ID. To retake the screenshots without
another analysis, set `DOCS_SESSION_ID` to that ID when running it again.
Use only a session made by this script with the same input and grid settings.
To record a known build revision, set `APP_REVISION` to the full commit hash
and `APP_SOURCE_DIRTY` to the actual checkout state when building, as described
in the [runtime guide](../../runtime_provenance.md).

The script checks readiness, image decoding, count consistency, reopening from
history, horizontal overflow and browser page errors. We still inspect the
images for clipped text, missing media and private information before using
them. A later UI change needs new screenshots and an updated capture record;
old pictures should not silently stand in for the new interface.

To stop only this demonstration stack, run from the repository root:

```bash
FRONTEND_PORT=8081 BACKEND_IMAGE=traffic-monitoring-backend:docs \
  docker compose -p traffic-docs -f docker-compose.app.yml -f docker-compose.gpu.yml down
```

This keeps its database and media volumes. Do not add `-v` when the saved example
is still needed. The browser-test baseline images elsewhere in the repository
use test fixtures; they are not substitutes for these live captures.
