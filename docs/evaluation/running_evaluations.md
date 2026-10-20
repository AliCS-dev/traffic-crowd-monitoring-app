# Running Evaluations

[Documentation index](../README.md) | [Results index](results_index.md)

These commands reproduce the existing evaluation workflow. They require local
data, annotations and weights; cloning the repository alone is not enough.
The [dataset card](dataset_card.md) describes the data, and the
[protocol](evaluation_protocol.md) defines the historical measurements. The
separate [UAVDT development protocol](uavdt_daytime_protocol.md) has its own
preparation command, readiness check and fixed configuration; it is not a
completed v2 accuracy result. All commands run from the repository root.

## Running the Detector Evaluation

The evaluation dataset must pass its quality checks before we create a formal
model result:

```bash
.venv/bin/python scripts/validate_evaluation_dataset.py
```

We then run the configured validation protocol with one command:

```bash
.venv/bin/python scripts/run_detector_evaluation.py \
  --config configs/evaluation/yolo26n_validation.json
```

The command reads the dataset split, model settings, thresholds, timing policy,
and random seed from the configuration. Each run is stored under
`data/evaluation/derived/runs/<run-id>/`. The directory contains raw
predictions, metrics, timing measurements, environment provenance, checksums,
and a concise `summary.md` table.

The summary is derived entirely from the saved JSON files. We can rebuild it
without loading the model or rerunning inference:

```bash
.venv/bin/python scripts/render_evaluation_report.py \
  data/evaluation/derived/runs/<run-id>
```

For validation tuning, confidence thresholds are compared from the saved
confidence-floor predictions. This keeps model inference fixed while changing
only the operating threshold:

```bash
.venv/bin/python scripts/run_confidence_sweep.py \
  --source-run data/evaluation/derived/runs/<run-id>
```

The tracked sweep configuration contains only the five values declared in the
evaluation protocol. The command verifies every source-run checksum and refuses
held-out data before calculating the comparison.

The three predeclared inference image sizes are evaluated with:

```bash
.venv/bin/python scripts/run_image_size_benchmark.py
```

This runs the complete validation and timing protocol at `640`, `960`, and
`1280`. Each size receives its own normal evaluation run, and the command then
creates one checksum-backed comparison report. The configurations are checked
to ensure that only the image size and descriptive run name changed.

Representative detection and count errors are generated from a saved validation
run without repeating model inference:

```bash
.venv/bin/python scripts/run_error_analysis.py \
  --source-run data/evaluation/derived/runs/<run-id>
```

The analysis uses `pycocotools` operating matches for false positives and false
negatives, links overlapping wrong-class predictions as class confusions, and
also retains confusions with raw labels excluded by the taxonomy or an asset's
annotation scope. It keeps count-only crowd failures separate from box-level
errors and saves the complete machine-readable error list, deterministic
example images, contact sheets, a summary, and checksums under
`data/evaluation/derived/error_analysis/`.

The earlier YOLO26n selected baseline can still be reproduced as one complete
validation run with:

```bash
.venv/bin/python scripts/run_detector_evaluation.py \
  --config configs/evaluation/yolo26n_selected_validation.json
```

It remains historical comparison evidence rather than the application runtime
configuration. Image and video processing now use the separate validated
YOLO26m runtime profile described in the [local setup guide](../local_development.md). Neither evaluated model passed the
quality gate, and neither should be presented as deployment-ready.

Formal results should be created from a committed working tree on the same
documented hardware and power configuration. Generated run directories remain
outside Git because they contain large prediction and timing records.

We can validate the predeclared aerial-model shortlist without downloading any
weights:

```bash
.venv/bin/python scripts/validate_model_candidates.py
```

## Reviewing the Saved UAVDT Baseline

The separate [UAVDT error review](uavdt_error_review.md) reuses the tracked
18 October development run without loading a detector or changing annotations:

```bash
.venv/bin/python scripts/review_uavdt_predictions.py
```

It requires the original local run, prepared images, native annotations and
checkpoint file for identity verification, but no GPU or database. The command
checks source hashes and the original matching totals, then writes a timestamped
directory under `data/evaluation/derived/uavdt_error_review/`.

Each directory contains M0207 side-by-side images, selected bus/truck crops,
a contact sheet, full error records, counts and a checksum manifest. Generated
images and coordinates stay outside Git. The tracked compact report records
which review was inspected; rerunning the command does not replace that record
or produce a new accuracy result.
