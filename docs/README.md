# Documentation

We keep everyday use, implementation details and research evidence separate.
The [project README](../README.md) gives a short overview; the pages below
answer more specific questions.

## Using the Application

| Question | Guide |
| --- | --- |
| What does a complete analysis look like? | [Illustrated user guide](user_guide.md) |
| How do we run the browser, API and database together? | [Docker Compose](compose_stack.md) |
| How do we run Python and the frontend separately? | [Local development](local_development.md) |
| How do we submit requests without the browser? | [HTTP API](api.md) and [image CLI](command_line.md) |
| What do the count notifications mean? | [Experimental alert rules](alert_rules.md) |
| What happens when a job fails or reaches a limit? | [Operational safeguards](operational_safeguards.md) |

## Understanding and Changing the Code

| Topic | Reference |
| --- | --- |
| Containers, processing flows and design decisions | [Application architecture](architecture.md#the-running-application) |
| Image builds, storage and service startup order | [Docker lifecycle diagram](architecture.md#how-docker-builds-and-starts-the-app) |
| Tables, keys, column types and relationships | [Database ER diagram](database/database_schema.md#how-the-tables-are-connected) |
| Backend container and GPU setup | [Backend container](backend_container.md) |
| Checks, branches and dependency updates | [Development workflow](development_workflow.md) |
| Model and dependency details recorded with results | [Runtime provenance](runtime_provenance.md) |
| Screenshot sources and capture procedure | [Screenshot record](images/user-guide/README.md) |
| Interactive scene checks and live workflow results | [Scene workspace verification](scene_workspace_verification.md) |

## Writing the Thesis

The [evaluation results index](evaluation/results_index.md) is the starting
point for model metrics. It links each result to its protocol and supporting
records. A screenshot demonstrates the interface; it does not establish model
accuracy.

| Thesis material | Starting point |
| --- | --- |
| System Design and Implementation | [Architecture](architecture.md), [database schema](database/database_schema.md), [user guide](user_guide.md) |
| Materials and Methods | [Evaluation protocol](evaluation/evaluation_protocol.md) and [dataset card](evaluation/dataset_card.md) |
| Results and Discussion | [Results index](evaluation/results_index.md), including unsuccessful experiments and limitations |
| Reproduction commands | [Running evaluations](evaluation/running_evaluations.md) and [Docker Compose](compose_stack.md) |

Final whole-application measurements are still pending. Earlier deployment
checks are not a substitute for that evaluation. The
[quality roadmap](../quality_roadmap.md) records the remaining work.

## Research Plans and Historical Records

The [v2 plan](evaluation/evaluation_v2_plan.md),
[source inventory](evaluation/source_inventory_v2.md),
[annotation feasibility report](evaluation/annotation_feasibility_v2.md),
[UAVDT adapter](evaluation/uavdt_adapter.md) and
[media check](evaluation/uavdt_media_check.md) describe ongoing evaluation work,
not new accuracy scores.

The [development log](development_log.md) explains how the project changed.
The [dashboard verification](dashboard_verification.md) and
[runtime recovery](runtime_recovery.md) reports record checks on particular
dates. Their test counts, dependency versions and session IDs belong to those
checks, not necessarily to the current checkout.
