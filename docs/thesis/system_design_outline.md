# System Design and Implementation: Writing Outline

[Documentation index](../README.md) | [Architecture](../architecture.md)

This is a source-backed outline for issue #81, prepared on 28 October 2026.
It is not a completed LaTeX chapter. The LaTeX project is not present in this
repository, so we have not edited or compiled the thesis.

We can draft stable design sections now. Final performance tables and conclusions
belong to the later system evaluation and Results and Discussion chapter.

## Suggested Chapter Order

| Section | What we explain | Implementation evidence |
| --- | --- | --- |
| Requirements and scope | Image/video analysis, saved results, spatial counts, local use, explicit model limits | [User guide](../user_guide.md), [operational limits](../operational_safeguards.md) |
| Component architecture | Browser, HTTP API, processing services and database responsibilities | [Architecture and deployment diagrams](../architecture.md), `frontend/src/`, `app/api/`, `app/services/` |
| Repository structure | Why processing, persistence and presentation have separate modules | [Architecture](../architecture.md), `app/database/`, `tests/` |
| Image and video processing | Validation, scaling, detection, sampling, output generation and background video work | `app/services/image_analysis_service.py`, `app/services/video_analysis_service.py`, `app/services/video_detection_service.py` |
| Model configuration and provenance | Fixed profile, class mapping, checkpoint identity and saved runtime context | `app/model_profile.py`, `app/runtime_provenance.py`, [runtime guide](../runtime_provenance.md) |
| Spatial counts and alerts | Assignment to grid cells, stored summaries and configured threshold events | `app/services/grid_counting_service.py`, `app/services/alert_service.py`, [alert rules](../alert_rules.md) |
| Database design | Sessions, sources, frames, related records, migrations and transaction boundaries | [ER diagram](../database/database_schema.md), `app/database/detection_repository.py`, `app/database/video_job_repository.py` |
| API and result retrieval | Request validation, asynchronous job status, errors and controlled asset access | [API reference](../api.md), `app/api/routes/`, `app/database/monitoring_query_repository.py` |
| Browser workspace | Upload, progress, scene inspection, stored totals, filters and history | [Illustrated guide](../user_guide.md), `frontend/src/features/results/` |
| Deployment and safeguards | Containers, networking, volumes, startup order, GPU access and recovery | [Compose guide](../compose_stack.md), [operations guide](../operational_safeguards.md) |
| Testing and development | Controlled unit tests, PostgreSQL integration, browser checks, CI and local GPU verification | [Workflow](../development_workflow.md), [workspace verification](../scene_workspace_verification.md) |
| Limitations | Local deployment, experimental detection/alerts, no accepted dense-crowd counter | [Results index](../evaluation/results_index.md), [system evaluation plan](../evaluation/system_evaluation_plan.md) |

## Reasons and Trade-Offs to Explain

These are design arguments to develop in our own words, not evidence that the
selected tools outperform every alternative.

- **PostgreSQL:** sessions, frames and detections have clear relationships.
  Foreign keys and transactions support consistent writes. This introduces a
  separate service and migration work; it does not prove faster performance.
- **Python and FastAPI:** the detection pipeline already uses Python, so the API
  can call it without another language boundary. Native inference can block;
  bounded background work and admission limits matter.
- **React and MUI:** the browser has interactive selection and request state.
  Existing components keep the controls consistent, at the cost of a separate
  JavaScript build and dependency set.
- **Separate containers:** browser delivery, API processing and database storage
  have different runtime needs. Compose makes local setup repeatable, but GPU
  drivers and Docker/WSL integration remain host responsibilities.
- **Files plus relational metadata:** media bytes remain in volumes; PostgreSQL
  stores paths and relationships. Transactions do not make filesystem writes
  atomic, so failure cleanup and retention require explicit handling.
- **One bounded video worker:** this keeps the local application understandable
  and limits competing GPU work. It is not a horizontally scalable queue.
- **Clean processed media:** boxes and grids can be inspected without baked
  labels. We retain a second JPEG, which costs storage, and older results do not
  gain clean pixels automatically.

We should connect each choice to a requirement, explain its implementation and
name its limitation. General claims about technologies need primary references
in the thesis bibliography; repository files support claims about our code.
The final bibliography entries and university citation style still need checking.

## Figures We Already Have

The [architecture diagrams](../architecture.md) explain components and container
startup; the [database diagram](../database/database_schema.md) shows tables and
relationships. The [user guide](../user_guide.md) provides real desktop and mobile
screenshots with a [capture and attribution record](../images/user-guide/README.md).
A sequence figure for image submission and background video processing can be
derived from the code if the supervisor expects one; it is not supplied by this
outline.

Captions should explain the design point, identify the version where relevant,
and retain media attribution. A screenshot of predicted boxes illustrates the
interface, not the detector's accuracy.

## Wording Boundaries

We use consistent terms: a monitoring session contains input sources and
processed frames; detections and summaries belong to a frame. A source asset is
an unannotated processed JPEG, not necessarily the original uploaded bytes.
Counts across sampled frames are not unique tracked road users. Grid counts
are not calibrated people-per-square-metre density. Threshold alerts do not
establish real congestion, danger or emergency response.

We retain the failed detector quality gate and unsupported dense-crowd result.
We describe AI assistance in accordance with the university's actual rules and
our real workflow; we do not invent a policy or claim unaided authorship.
Ali should be able to explain each design decision and revise the prose in his
own voice.

The next writing step is a short draft of requirements and system architecture,
using these figures and checked sources. We can then add processing and database
sections incrementally. Issue #81 stays open until the actual chapter is reviewed
and the LaTeX build and references have been checked.
