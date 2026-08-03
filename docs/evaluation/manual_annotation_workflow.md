# Wikimedia Manual Annotation Workflow

## Purpose

The independent Wikimedia traffic examples do not include publisher-supplied
bounding boxes. We annotate them manually before they enter any metric. This
keeps an unlabelled image from being interpreted as an empty road scene and
gives the held-out traffic evaluation an independent location.

The initial task contains two Renai roundabout images and ten sampled Jane Byrne
Interchange frames. The Renai day and night images remain one validation source
group, while every Jane Byrne frame remains in one held-out source group.

Four Jane Byrne frames (`609`, `702`, `796`, and `890`) were excluded before
benchmarking because their manual ground-truth pass was not completed. They are
recorded in `data/evaluation/exclusions.csv` and cannot enter a quantitative
metric with their partial draft boxes. The retained manual set therefore has two
Renai images and six Jane Byrne frames.

## Preparing The Task

We build the model-assisted CVAT COCO package with:

```bash
.venv/bin/python scripts/prepare_manual_annotation_task.py
```

The resulting local archive is:

```text
data/evaluation/derived/manual_annotation/
  wikimedia_manual_v1_draft_cvat.zip
```

The draft uses `models/yolo26n.pt` at confidence `0.15` and image size `1920`.
Its model SHA-256, settings, prediction confidence, and draft status are stored
inside the COCO file. These boxes are annotation assistance, not ground truth.

We can also produce a task with no model suggestions:

```bash
.venv/bin/python scripts/prepare_manual_annotation_task.py \
  --without-draft-boxes
```

This creates `wikimedia_manual_v1_blank_cvat.zip`. Keeping both versions lets us
choose efficiency or annotation independence without confusing the two.

## Review Standard

We use the class and box rules in
[`annotation_guide.md`](annotation_guide.md). For every image, we inspect the
complete frame systematically from top left to bottom right and then repeat the
scan in the opposite direction.

During the first annotation pass, we:

- add every identifiable target vehicle missed by the draft;
- delete boxes placed on buildings, signs, shadows, or road markings;
- correct bus, truck, car or van, motorcycle, and bicycle assignments;
- tighten boxes to the visible object rather than its shadow;
- inspect every road level, ramp, parking area, and image boundary; and
- retain visible stationary vehicles consistently with the annotation guide.

The current model has low recall on small interchange vehicles. Its draft boxes
must never be accepted in bulk. A reviewer must also inspect locations where the
draft shows no box.

When the first pass is complete, we export COCO detection annotations from CVAT
without changing task filenames or category identifiers. We keep the reviewed
export locally under:

```text
data/evaluation/derived/manual_annotation/reviewed/
```

The tracked `data/evaluation/manual_annotation_exports.csv` row records the
export date, tool, format, archive SHA-256, and inner annotation JSON SHA-256.
Running the normal conversion command verifies both checksums, matches images by
stable asset ID and dimensions, rejects unknown labels or images, and merges the
retained boxes into the role-level canonical COCO files:

```bash
.venv/bin/python scripts/convert_evaluation_annotations.py
```

CVAT can preserve rotated rectangles in its custom `rotation` attribute. The
canonical benchmark uses axis-aligned detector boxes, so the importer converts
each rotated rectangle to its enclosing axis-aligned box and clips boundary
objects to valid image coordinates. The source rotation remains attached to the
box provenance. The generated import report is stored at
`data/evaluation/derived/reports/manual_annotation_import.json`.

The reviewed export remains separate from the final quality-control decision.
A second visual pass uses freshly rendered overlays, records corrections in
`data/evaluation/qc_reviews.csv`, and states whether the reviewer was the same
researcher who completed the first pass.

We do not edit the reviewed CVAT archive after its checksum has been recorded.
Confirmed duplicate removals and class corrections are listed by their original
CVAT annotation ID in `data/evaluation/manual_annotation_corrections.csv`. The
importer validates this ledger and applies it while rebuilding the canonical
COCO files. This preserves both the original export and the exact changes made
during quality control.

## Reproducibility And Attribution

The task asset table retains the source URL, creator, licence, dataset role,
source group, and image SHA-256 for every image. The images and task archives
remain outside Git. We track the preparation code and later record the reviewed
annotation-file checksum so the thesis can identify the exact ground-truth
version without redistributing the media.
