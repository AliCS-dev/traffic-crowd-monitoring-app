# UAVDT Daytime Development Baseline

**15 October 2026, issue #113.** This is a separate three-class development
evaluation against UAVDT's existing labels. We fixed the sample and baseline
settings before running predictions. It does not replace the six-class v2 plan,
establish a new independent final holdout, or change the historical failed gate.

The machine-readable [protocol](../../data/evaluation/uavdt_daytime_protocol.json)
lists every selected sequence and frame, source hashes and the baseline
configuration hash. The [configuration](../../configs/evaluation/uavdt_daytime_baseline.json)
contains the settings consumed by the evaluator. No new accuracy result has
been produced by preparing these files.

**18 October completion:** all 170 selected images are present and the
source-specific readiness check passes. The
[preparation record](../../data/evaluation/uavdt_daytime_preparation.json)
contains the manifest and annotation hashes, per-sequence counts and source-label
warnings. This establishes technical readiness for the fixed development
baseline, not model accuracy or independently reviewed ground truth.

## Prepared Sample

| Measure | Observed value |
| --- | ---: |
| Images / source training sequences | 170 / 17 |
| Decoded dimensions, every image | 1024 x 540 |
| Car/van labels / sequences containing them | 2,804 / 17 |
| Truck labels / sequences containing them | 164 / 15 |
| Bus labels / sequences containing them | 91 / 9 |
| Total labelled instances | 3,059 |
| Ignored rectangles | 371 |
| Exact duplicate image hashes | 0 |
| Out-of-bounds target boxes | 0 |
| Labelled boxes strictly inside an ignored rectangle | 10 |

These are annotation inventory counts, not predictions or distinct vehicles.
Repeated observations within a sequence are correlated. For example, 46 of the
91 bus labels come from `M0702`, so the bus sample is concentrated despite
covering nine sequences. Exact-file uniqueness does not rule out near-duplicates.

The ten labels inside ignored rectangles occur in `M0301` frame 253, `M0401`
frame 613 and `M1304` frame 1205. We retain them under the fixed source policy.
Predictions strictly inside those rectangles will be excluded while the labels
remain targets, which can introduce false negatives and count disagreement even
for correctly localized predictions. The preparation record lists all ten
identities; the readiness output reports their count. The two earlier `M0210`
concerns also remain unchanged. No independent human annotation review is claimed.

## What We Measure

We use all 17 sequences marked as daylight, without night or fog, in the
recorded source training split. From each sequence we select ten frames:

```text
frame(i) = 1 + floor(i * (N - 1) / 9), for i = 0, ..., 9
```

Here `N` is the last labelled frame. The source labels must cover every frame
from 1 to `N`. This gives 170 images, with the first and last frame included.
The rule does not use model predictions, object difficulty or selected scores.
Ten frames limit repeated observations within a sequence; they do not make
those observations independent. Sequence IDs are not verified capture locations.
Daylight attributes also do not establish rain-free conditions.

All selected images have the project role `validation`, even though their
original UAVDT role is `train`. We will use them to understand the baseline and
guide later development, not to claim untouched test performance. All 12
daytime source test sequences remain reserved; this preparation command cannot
download them, and this protocol cannot authorize a held-out evaluation.

The targets are `car_or_van`, `truck` and `bus`. Native UAVDT `car` maps to our
`car_or_van` class; that is a class-alignment assumption, not separate van
annotation. Person and two-wheeler predictions remain outside these scores.
Here, `road_vehicle_total` means these three classes only. It is not directly
comparable to the historical five-vehicle-class total.

Using every daytime training sequence for development leaves none of those
sequences available for a disjoint fine-tuning split within this protocol.
Any later training proposal needs a separate, documented split or source. We
must also check candidate pretraining exposure and cross-sequence scene overlap
before claiming an independent final comparison. Unknown exposure stays unknown.

## The Source-Label Decision

The [nine-image check](uavdt_media_check.md) identified two questionable records
in `M0210`, frame 583: tracks 34 and 18. One large car box covers vegetation and
road; another lies over the toll canopy, where its target cannot be identified
from the still image. Both native records say no occlusion. Our visual inspection
does not provide enough evidence to reconstruct their intended ground truth.

We therefore retain both records, the frame and the sequence. We also retain
all other native DET boxes and all native occlusion/out-of-view codes. We do not
repair boxes, discard difficult objects or apply a new visible-only filter.
Frame 583 is included by the fixed sampling rule. These concerns are recorded
limitations of the reference labels, not corrections approved by Ali.

This choice makes the first result a measurement of **agreement with the native
source labels**, not proof that every labelled object is visually identifiable.
Possible annotation mistakes can affect precision, recall and counts. A later
label correction would need a versioned audit trail and separate results; it
must not silently replace this baseline after predictions have been inspected.

We retain the tested [strict-containment ignore rule](uavdt_adapter.md#exclusion-rule).
Only predictions strictly inside an ignored rectangle are excluded. Native DET
boxes remain targets, even if they overlap an ignore region. We report any
strictly contained ground-truth boxes and out-of-bounds source boxes during
preparation rather than clipping or deleting them. Counts are source-defined
per-frame counts, not every visible vehicle or unique vehicles over time.

No independent human annotation review is claimed or assigned to Ali. The
mirror has recorded hashes, but equivalence to the publisher's original copy
has not been established. Research-use restrictions remain in force. Source
images, native labels and converted box coordinates stay outside Git; permission
to reproduce images in the public thesis still needs checking.

## Fixed Baseline Settings

We reuse the selected application's YOLO26m VisDrone checkpoint, with SHA-256
`e57204b8d77b5b22ea9253cbd5664b707623aeb7c19dbaa9034fe5a60bed6571`.
The baseline is not a model-selection exercise.

| Setting | Value |
| --- | --- |
| Random seed | 2026 |
| AP prediction confidence floor | 0.001 |
| Operating confidence | 0.25 |
| Operating matching IoU | 0.50 |
| Inference image size / preprocessing scale | 1280 / 2 |
| Device / precision / batch size | `cuda:0` / float32 / 1 |
| Maximum detections per image | 300 |
| Low-support warning | Fewer than 20 source boxes per class |
| Timing | 20 warm-up frames, 100 measured frames, 3 repetitions |

The existing evaluator produces class-aware COCO AP50/AP50-95, operating
precision/recall, count MAE/NAE and bias, and separate runtime measurements.
These are project subset results, **not official UAVDT challenge scores**.
Raw predictions, settings, software/hardware provenance and artifact hashes
remain in the saved run. The readiness record is also attached to provenance.

This step authorizes one baseline configuration only, with no confidence sweep,
resolution search, training or model adoption. We will report the baseline even
if it is poor. There is no new pass threshold that can turn the historical
failed gate into a pass. Before #114 experiments, we must declare candidate
budgets and selection rules separately. GPU resource failures must be reported;
we will not silently switch devices, precision or sample membership to finish.

## Preparing and Checking the Data

The preparation script needs the retained attribute archive recorded in the
[source inspection](annotation_feasibility_v2.md), the tracked protocol, and
network access to the pinned mirror. It downloads only selected training media
and their labels using exact HTTP byte ranges. Toolkit and media budgets are
32 MB and 384 MB, respectively; a full-archive fallback is not allowed.

```bash
.venv/bin/python scripts/prepare_uavdt_evaluation.py
```

The output is `data/evaluation/raw/uavdt_daytime_v1/`, containing images, native
files, `manifest.csv`, `instances_validation.json`, `preparation.json` and
download-range logs. Existing output is never overwritten. An interrupted
acquisition can continue explicitly with:

```bash
.venv/bin/python scripts/prepare_uavdt_evaluation.py --resume
```

Resume verifies source-file hashes and cached image sizes/ZIP CRCs, then decodes
the images again. A mismatched cached file causes an error rather than automatic
replacement. Resume is refused after conversion has begun. Incomplete data is
not ready for evaluation. Each attempt now records its completed HTTP ranges;
the first interrupted acquisition preceded that logging change, so we do not
claim a complete cumulative download-byte total for this session.

On 18 October, acquisition resumed from the 28 images retained on 15 October.
Intermittent DNS and connection failures recurred. A temporary local helper used
`requests.Session` to reuse connections for the final acquisition attempt;
the repository's transport implementation and system DNS settings were not
changed. TLS verification, exact HTTP ranges, byte budgets, ZIP CRCs and source
hash checks remained enabled. The final attempt reused 55 cached images and
retrieved 29,102,568 successful range-payload bytes, not the complete archives.
This byte count excludes earlier attempts and is not a network-performance metric.

The completed `preparation.json` is reviewed and retained as
`data/evaluation/uavdt_daytime_preparation.json` in Git before the evaluator is
enabled. The completed receipt is now included. The validator compares it with
the actual manifest and annotations, checks source and image hashes, decodes each image,
and rebuilds annotations in memory to detect any departure from native labels.
It rejects changed selection, duplicate image bytes, wrong roles or classes,
edited labels and a different checkpoint. It cannot prove semantic label
correctness, detect every near-duplicate, or establish independent locations.

```bash
.venv/bin/python scripts/validate_uavdt_evaluation.py
```

Success means `ready_for_source_label_development_baseline_only`. It is neither
a model-quality pass nor certification of the wider v2 dataset. The older
historical validator does not authorize this source-specific dataset.

Local verification on 18 October passed with 548 Python tests; 11 opt-in database
tests were skipped locally. Lint, formatting, Python compilation and installed
dependency checks passed. The real-data validator rechecked all 170 images,
all 51 native source files, the canonical labels and the checkpoint. A separate
check confirmed that the known `M0210` records remain in the selected final frame.

After the preparation record and code have been reviewed and committed, the
next step is the actual baseline run on the documented GPU environment:

```bash
.venv/bin/python scripts/run_detector_evaluation.py \
  --config configs/evaluation/uavdt_daytime_baseline.json
```

Results will be saved under `data/evaluation/derived/uavdt_daytime_runs/` and
linked from the [results index](results_index.md). This command has not been run
as part of data preparation. We will record measured results there rather than
copying guessed or sample-derived accuracy into the thesis.
