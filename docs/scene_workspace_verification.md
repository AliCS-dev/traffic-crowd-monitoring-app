# Scene Workspace Verification

[Documentation index](README.md) | [Illustrated guide](user_guide.md)

We checked issue #116 on 26-27 October 2026. This work makes saved results
easier to inspect. It does not improve the detector or establish counting
accuracy. The [evaluation index](evaluation/results_index.md) remains the
source for model metrics and their limitations.

## What Changed

The result view gives more room to the image and keeps the selection inspector
beside it on desktop, or below it on mobile. Detection boxes and grid cells
share the image's pan and zoom transform. Class and display-confidence filters
change the visible detection records without rewriting saved summaries,
inference settings or alerts. Selecting a box also selects its table row;
selecting a grid cell shows that cell's stored counts.

New API analyses retain a clean processed JPEG alongside the annotated JPEG.
Migration 009 adds one nullable path column; the existing UUID identifies both
assets. Both routes enforce the same allowed-directory checks. The clean JPEG
has the detection coordinate dimensions, but is not the original upload byte
for byte. Older results keep their annotated preview, with its limitations
labelled. Reading a result does not rerun inference or generate missing files.

We reused React, MUI and the existing API. No new frontend dependency was
needed. Ali's God's Eye reference informed the scene-first layout; we did not
copy its code, branding or imagery. The real screenshot input and its licence
are documented in the [capture record](images/user-guide/README.md).

## Automated Checks

| Check | Result on 27 October |
| --- | --- |
| Python tests, including PostgreSQL integration | 594 passed, including 12 database checks |
| Frontend unit and component tests | 115 passed |
| Chromium desktop/mobile browser tests | 14 passed |
| Live Compose image/video browser tests | 4 passed |
| Frozen five-frame GPU regression | Passed with no differences |

The database tests include fresh installation, repeat migration, preservation
of older frames and the constraint linking source images to output assets.
Other tests cover asset-path boundaries, failed-write cleanup, retained source
files, missing media, decoded-image dimension mismatches and filter semantics.

The browser suite checks box and grid alignment through zoom, pan and resize,
keyboard selection, touch dragging, frame navigation and horizontal overflow.
Desktop screenshots use 1440 by 1000 pixels; the narrow layout uses 320 by 900.
We inspected the changed screenshots and then ran the suite without updating
its baselines. These browser fixtures contain synthetic records, clearly named
as fixtures; they are not evaluation annotations or detector evidence.

With 300 fixture detections, the class-filter check took **128.6 ms on desktop**
and **126.1 ms on mobile**, below its fixed 2000 ms budget. These measurements
include Playwright interaction and assertion overhead on this WSL machine.
They are a regression guard, not rendering-only timings, inference throughput
or evidence of performance on a physical phone. The budget test remains in
`frontend/e2e/scene-workspace.spec.ts` and records each duration as an annotation.

## Live Results

We used the isolated `traffic-issue116` Compose project, PostgreSQL 16 and the
RTX 5060 Laptop GPU on `cuda:0`. The application was a working branch build,
recorded as modified source rather than a clean release. Its backend source
hash is `6038263cfbfe1ee6745b8124bc9d9e31bf4944fc63090021ea5ac578fc72df33`.

| Workflow | Development sessions | Observed result |
| --- | --- | --- |
| Image upload, saved result and history | 13 and 15 | 94 detections and six grid cells on both layouts |
| Video upload and sampled-frame navigation | 14 and 16 | Three samples with 21, 24 and 30 detections on both layouts |
| Documentation image | 4 | 27 detections and six grid cells; real desktop/mobile captures |

Both image runs produced the same annotated JPEG hash:
`2085acac65230307033f292b1752bb0f1ddc08694f6fc37e9cd822d56ee46b03`.
Video checks fetched both image variants for each sample and verified that
navigation changes the clean image and overlays together, resetting zoom.
Session IDs belong to this disposable development database, not portable
fixtures. The counts above describe predictions, not reference labels.

The unchanged runtime regression used two images and three video samples from
the [fixed fixture set](../data/runtime-regression/README.md). It reported no
differences against the frozen baseline. We did not replace historical runtime
or accuracy records. The [screenshot receipt](images/user-guide/capture.json)
records the actual media, backend, frontend-entry and screenshot hashes.

## Repeating the Checks

After the normal [local setup](local_development.md), we run Python checks from
the repository root and browser checks from `frontend/`. Database integration
uses a separate test database, never the application database.

```bash
RUN_DATABASE_INTEGRATION_TESTS=1 DATABASE_URL=<test-database-url> python -m pytest -q
cd frontend
npm test
npm run test:browser
STACK_BASE_URL=http://localhost:8083 STACK_IMAGE=../data/input/sample_image.jpg npm run test:stack
```

The live suite needs the [Compose prerequisites](compose_stack.md#first-start)
and a ready GPU backend. `STACK_IMAGE` is required for its image test; the video
test uses the tracked, attributed roundabout fixture. From the repository root,
the frozen comparison can be repeated without overwriting its baseline:

```bash
python scripts/check_runtime_regression.py --base-url http://localhost:8083 --output /tmp/scene-runtime-check.json
```

## Remaining Limits

The detector still failed its quality gate, dense-crowd counting remains
unsupported, and threshold alerts remain experimental. No accuracy issue was
closed by this interface work. Browser automation covers Chromium, not every
browser or assistive technology. Touch checks use emulation, not a physical
device, and contrast/focus inspection is not an accessibility certification.
Final whole-application evaluation remains under #79 after the release freeze.
