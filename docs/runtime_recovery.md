# Runtime Recovery: 15 September 2026

## What Changed

Issue #111 addresses the immediate findings after the September 15 project
review. We started from GitHub main `500ff26`, including its merged dependency
updates. We did not replace the selected model or rerun the held-out evaluation.

The backend requirements paired `pydantic==2.13.5` with an incompatible
`pydantic-core==2.49.0`. Pydantic requires core `2.46.5`; restoring that pin made
the image buildable. We also pinned the newly introduced transitive dependencies
from the resolved Ultralytics runtime. The complete image build includes
`pip check`.

CI previously ran `docker build --check`, which validates the Dockerfile but
does not install its requirements. It now builds the backend image and runs
dependency and application-import checks without requiring CUDA hardware.
The frontend uses Node 26 in `.nvmrc`, CI and its existing pinned builder;
the Docker build rejects a mismatched major version.

The stopped local backend reported a missing Docker Desktop WSL bind-mount path.
Recreating the service restored the model mount. We kept the original database,
uploads and output volumes; the separate development database on port 5433 was
not used for integration tests or deleted.

## Verification Scope

We used the isolated `traffic-stack-check` Compose project and safe values from
`.env.example`. The current backend contains PyTorch `2.14.0+cu130`,
Ultralytics `8.4.147`, OpenCV `5.0.0.93`, NumPy `2.5.3`, Pydantic `2.13.5` and
core `2.46.5`. The selected checkpoint remains VisDrone YOLO26m, SHA-256
`e57204b8d77b5b22ea9253cbd5664b707623aeb7c19dbaa9034fe5a60bed6571`.

| Check | Observed result |
| --- | --- |
| Backend and frontend image builds | Passed |
| Installed dependency check and backend imports | Passed |
| CPU and GPU Compose configuration validation | Passed |
| Restored frontend, backend and PostgreSQL | Healthy; migration service completed |
| RTX 5060 synthetic inference | Passed on `cuda:0` |
| CPU-selected synthetic inference | Passed on `cpu` in the GPU-capable image |
| Python regression tests | 365 passed |
| PostgreSQL integration tests | Nine passed against a disposable database on port 5544 |
| Frontend unit tests | 103 passed |
| Existing mocked browser tests | Eight passed |
| Existing session retrieval on desktop and mobile | Two passed; original output hash unchanged |
| Fresh desktop and mobile uploads | Two passed; 94 detections and six grid cells each |

The existing session 1 still has 92 detections, six grid cells and output hash
`fc029d31549468eaf8dc8db750fc01635d96b22feb7af1dbda1985ac523a0363`.
This checks persistence, not equivalence between model predictions under two
runtime versions. The Python regression suite used the existing local virtual
environment; container checks exercised the pinned runtime directly.

Fresh sessions 3 and 4 used the same `data/input/sample_image.jpg` but produced
94 detections rather than the older runtime's 92. Their output SHA-256 was
`fccec45e23e5fd5124016f6903c12cfb23492823ecbeeedd7e96feebd005c01d`.
This observed drift is not an accuracy improvement or a new quality-gate result.
We have not isolated which changed dependency caused it. Historical results stay
unchanged; #112 must establish a reviewed runtime regression baseline before new
accuracy experiments rely on this environment.

The complete-stack commands and browser checks are in
[Full Application Compose](compose_stack.md). The live test's screenshots and
JSON attachments are generated under `frontend/test-results/stack/` and are
ignored by Git. Issue #112 covers durable environment provenance and a reviewed
prediction-regression protocol for future updates.

## Limits

Successful deployment checks do not establish detection accuracy. The
[model quality gate](evaluation/final_quality_gate.md) is still failed and the
[dense-crowd decision](evaluation/dedicated_crowd_counting_result.md) remains
unsupported. Their published metrics belong to their recorded environments,
not automatically to these newer packages. Resource safeguards (#80), broader
workflow coverage (#26) and final system measurements (#79) remain open.
