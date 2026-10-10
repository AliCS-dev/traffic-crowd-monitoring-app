# UAVDT Annotation And Ignore Handling

**10 October 2026, issue #113.** Ali approved implementation of a separate
daytime UAVDT car/truck/bus evaluation after the
[annotation feasibility inspection](annotation_feasibility_v2.md). We have added
the annotation adapter and tested scoring support. We have not acquired media,
selected final frames, run inference, trained a model or measured new accuracy.
The six-class plan and historical failed quality gate remain unchanged.

## What Is Implemented

The [adapter](../../evaluation/uavdt_annotations.py) reads DET
`Mxxxx_gt_whole.txt`, separate `Mxxxx_gt_ignore.txt` files and the release's
training/test sequence attributes. We preserve frame and track IDs, native
class IDs, out-of-view and occlusion codes, their explicit meanings and
sequence attributes in the converted JSON. Source-file and image SHA-256
hashes identify the inputs. These are publisher labels from a recorded mirror,
not annotations independently reviewed by Ali.

| Native class | Project class | Canonical ID |
| --- | --- | ---: |
| 1: car | car_or_van | 4 |
| 2: truck | truck | 6 |
| 3: bus | bus | 5 |

Mapping model `car_or_van` predictions to source `car` is an alignment assumption,
not evidence of a separately annotated van category. Person, bicycle and
motorcycle predictions are outside this source-specific comparison. The
`road_vehicle_total` metric therefore covers only car/van, truck and bus here.

We retain source `(left, top, width, height)` coordinates without resizing,
clipping or adding/subtracting one. The inspected toolkit also passes these
values directly to matching. Frame IDs remain 1-based. Correct correspondence
to media and pixel boundaries still needs checking; a parseable file is not
proof of correct visual alignment. The application prediction path clips boxes
to image bounds, another reason not to claim identical official scores.

## Exclusion Rule

The canonical JSON has an explicit `ignore_policy` of
`uavdt_strict_containment_v1` and an `ignored_regions` list. These are project
extensions, not standard COCO crowd annotations. Unsupported COCO `iscrowd=1`
or `ignore=1` boxes now fail clearly instead of being scored as normal targets.

For a prediction and an ignore rectangle in the same frame, we exclude the
prediction only when **all four prediction edges lie strictly inside** the
rectangle. A touching edge, equal rectangle or partial overlap does not qualify.
We do not use an IoU or intersection-over-area threshold, combine rectangles
into a mask, or change the exclusion with confidence or AP matching thresholds.
Ignored predictions are removed before COCO matching and detection limits.

Both detection and count metrics use this rule; qualitative detection-error
analysis uses it too. Labelled DET boxes are retained, including any overlapping
an ignored area. If a labelled object is fully inside an exclusion, the source
policy can still leave a false negative; we do not erase the label to improve
the score. Such conflicts should be disclosed during media checks.
Raw prediction records are not rewritten. Dataset subsets retain their regions
and policy. Historical datasets without regions keep their original behavior.

### Source And Differences

We inspected `utils/CalculateDetectionPR_overall.m`, `CalculateDetectionPR_obj.m`
and `CalculateDetectionPR_seq.m` in the
[pinned UAVDT toolkit mirror](https://huggingface.co/datasets/vanthanh/UAVDT-Benchmark-M/tree/ad1cfbe161c183cfdee26f6c42c6fff6552a54dc).
All three use strict containment to remove detections before matching and retain
the DET ground truth. We fetched only ZIP bytes `245125282-245130000` (4,719 bytes).
The retained local range and extracted overall evaluator identify the observation:

| Artifact | SHA-256 |
| --- | --- |
| Evaluator byte range | `01b3490a786a61c30d070775d7ab7e580fef2ad443f32042609f137898764169` |
| `CalculateDetectionPR_overall.m` | `cdae04ff798548e9079844276baed9be984c7b5a00c2aef91e37f55e5ddb0fe8` |

No MATLAB code was executed or copied into the project. Mirror provenance,
publisher-equivalence uncertainty and research-use restrictions remain as
described in the feasibility report.

The toolkit lists sequences with ignore files; our adapter instead requires
every selected sequence's ignore file and processes its rows. An existing empty
ignore file is valid; a missing file is not assumed empty. Our metrics use the
existing **class-aware COCO AP50/AP50-95** implementation, not the toolkit's
VOC-style PR integration. Daytime subset scores, when produced, must be labelled
as project evaluations and cannot be compared directly to official challenge AP.

## Conversion Contract

We use a separate manifest whose version begins with `uavdt-`, for example
`uavdt-day-v1`. It contains the existing evaluator's required manifest fields,
plus `frame_number`, `source_split` (`train` or `test`) and `image_sha256`.
`collection_id` is `uavdt`; `source_group_id` is the native `Mxxxx` sequence ID;
`target_classes` is `car_or_van;bus;truck`. All three classes remain targets even
when one has no boxes in a selected frame.

The converter verifies:

- Exact image hashes, decodability and dimensions for selected frames.
- Nine integer DET fields, valid codes, positive sizes and unique frame/track IDs.
- Daylight present with night/fog absent; this is not a verified rain-free filter.
- Official training/test membership and no sequence shared across dataset roles.
- No duplicate asset or sequence/frame pair, including across roles.
- A matching DET record for each selected frame. We do not infer a negative
  example from an absent row or file; confirmed empty-frame support is deferred.
- Repository-relative paths and a new output file. Existing outputs are never
  overwritten. The selected manifest's canonical annotation path must match it.

Source `test` sequences can only have role `held_out_test`. Training sequences
can have role `training` or `validation`, but not both within this manifest.
This prevents sequence leakage, not unverified physical-location overlap.
The adapter does not prove image identity from a filename, cross-sequence
independence, complete annotation coverage or freedom from model pretraining.

After media verification and a recorded selection exist, the command shape is:

```bash
.venv/bin/python scripts/convert_uavdt_annotations.py \
  --manifest data/evaluation/uavdt/manifest.csv \
  --gt-directory data/evaluation/raw/uavdt/GT \
  --attributes-directory data/evaluation/raw/uavdt/M_attr \
  --role validation \
  --output data/evaluation/derived/uavdt/instances_validation.json
```

These are future example paths, not files created in this step. `--help` works
now. The shared loader and metric functions support converted data. The full
`run_detector_evaluation.py` command deliberately rejects source-ignore datasets
until its historical readiness checks are replaced with source-specific checks
and a frozen run protocol. We cannot treat a passing v1 check as v2 readiness.

## Verification And Next Step

Synthetic tests cover the converter CLI, loader round trip, source class mapping,
attribute codes, split leakage, invalid/missing inputs, hash/dimension mismatch,
overwrite protection, strict-boundary exclusions, per-image isolation, retained
ground truth, matching/count/error-analysis consistency and unchanged no-ignore
metrics. Nonfinite box geometry is rejected at the shared data boundary.

Local verification passed with 494 tests and 11 opt-in database tests skipped.
Lint, formatting, dependency consistency and Python compilation passed. The
historical dataset's technical validator also passed; that result does not
certify the new UAVDT selection or change the historical accuracy gate.

The new parser also read the retained real annotation inputs, without opening
media or running a model:

| Technical validation | Observed count |
| --- | ---: |
| DET files / object rows | 50 / 798,795 |
| Ignore files / region rows | 50 / 90,387 |
| Attribute files | 50 |
| Daytime training / test sequences | 17 / 12 |

These totals include non-daytime sequences in the first three rows. They are
format-validation evidence, not new labels, independent objects or accuracy
measurements. ZIP CRC reads succeeded; original-publisher equivalence and
annotation correctness remain unverified.

Next we need a bounded media-access check, image/label overlays, an explicit
frame-selection rule and a frozen source-specific evaluation configuration.
Test sequences remain reserved for the final comparison, not development smoke
fixtures. We have not assigned Ali a manual annotation campaign. Issue #113
remains in progress, with its wider coverage and holdout requirements unresolved.
