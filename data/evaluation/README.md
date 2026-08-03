# Evaluation Data

This directory holds the metadata for the aerial data used in our model-quality
gate. The images and videos themselves stay on the local machine because they
are large and remain subject to their original licences.

The evaluation protocol is defined in
[`docs/evaluation/evaluation_protocol.md`](../../docs/evaluation/evaluation_protocol.md),
and the selected collections and their limitations are described in
[`docs/evaluation/dataset_card.md`](../../docs/evaluation/dataset_card.md).
Our class definitions, bounding-box rules, review process, and canonical COCO
format are recorded in
[`docs/evaluation/annotation_guide.md`](../../docs/evaluation/annotation_guide.md).
The separate workflow for the manually labelled Wikimedia examples is
described in
[`docs/evaluation/manual_annotation_workflow.md`](../../docs/evaluation/manual_annotation_workflow.md).

## Directory Layout

```text
data/evaluation/
├── README.md
├── downloads.csv         # Downloaded source packages and checksums
├── exclusions.csv        # Pre-benchmark exclusions and reasons
├── manual_annotation_corrections.csv # Auditable corrections to reviewed boxes
├── manual_annotation_exports.csv # Reviewed export checksums and provenance
├── manifest.csv          # Selected evaluation examples
├── selection_plan.csv    # Source groups, roles, and sampling decisions
├── derived/              # Extracted evaluation frames; ignored by Git
└── raw/                  # Publisher media; ignored by Git
    ├── traffic_uav/
    ├── dlr_acd/
    ├── okutama_action/
    └── wikimedia/
```

The local `raw` directory currently contains the three verified Traffic UAV
archives, the published Okutama train and test frame sets, the complete DLR-ACD
archive, and four Wikimedia Commons assets. We do not commit downloaded
archives, extracted images, videos, or copies of external annotations.

`downloads.csv` records the source packages and original media obtained from
publishers, together with the checksums used to verify them. `manifest.csv` has
a different role: it will record only the images or sampled video frames
selected for evaluation. Keeping these records separate prevents a downloaded
ZIP archive from being mistaken for one evaluation example.

The download log keeps the human-readable source page separate from the direct
file URL. It also records the publisher, creator, licence, intended use, local
path, file size, and checksum. This gives every acquired source a traceable
provenance record before individual evaluation assets are selected.

## Collection Identifiers

We use short, stable identifiers in the manifest:

| Identifier | Collection |
| --- | --- |
| `traffic_uav` | Traffic Images Captured from UAVs |
| `dlr_acd` | DLR Aerial Crowd Dataset |
| `okutama_action` | Okutama-Action |
| `wikimedia` | Individually licensed Wikimedia Commons media |

An `asset_id` identifies one original image or video. A `source_group_id`
connects related material from the same video, flight, scene, or capture
sequence. This grouping will later prevent closely related frames from being
placed in different dataset partitions.

Identifiers use lowercase snake case and do not change after an asset has been
added. Original filenames are preserved in their own manifest column.

## Recording A Download

For each source package, we:

1. confirm the licence on the official source page;
2. keep the original filename and record both its source page and download URL;
3. store the file below the matching collection directory;
4. compare the publisher checksum when one is available;
5. calculate a SHA-256 checksum;
6. add one row to `downloads.csv`; and
7. test the archive before extracting it.

For each image or sampled video frame later selected from those packages, we
will:

1. assign an `asset_id` and `source_group_id`;
2. add one row to `manifest.csv`;
3. retain the original filename and collection relationship; and
4. record any attribution or use restriction in the notes.

The checksum can be calculated with:

```bash
sha256sum data/evaluation/raw/<collection>/<filename>
```

## Selected Evaluation Subset

`selection_plan.csv` records the source-level decision before individual frames
are prepared. It keeps paired Okutama drone views together, groups both urban
traffic sequences from the shared location, and preserves the published
Okutama and DLR test roles. Midpoint sampling spreads selected frames evenly
through each sequence without using model predictions or annotation counts.

The selection plan produces 350 candidate examples. Four incompletely annotated
Wikimedia video frames were excluded before benchmarking, leaving 346 retained
examples:

| Collection | Examples | Main purpose |
| --- | ---: | --- |
| Traffic UAV | 90 | Vehicle bounding-box evaluation |
| Okutama-Action | 215 | Person bounding-box evaluation |
| DLR-ACD | 33 | Dense-crowd count evaluation |
| Wikimedia Commons | 8 | Independent traffic conditions |

The retained role totals are 130 training, 86 validation, and 130 held-out test
examples.
Every source group belongs to only one role. The training role currently
contains Okutama people only; it is not presented as sufficient vehicle-training
material. If later benchmarking justifies vehicle fine-tuning, we will add
independent licensed training sources rather than reuse validation or held-out
traffic scenes.

We rebuild the manifest and locally extract the ten candidate Wikimedia video
frames with:

```bash
.venv/bin/python scripts/build_evaluation_manifest.py
```

The command verifies source files and annotation references, applies the dated
records in `exclusions.csv`, records image dimensions and SHA-256 checksums, and
writes the deterministic retained selection to `manifest.csv`. This distinction
matters for Okutama because its downloaded 720p frames use labels expressed in
the original 4K coordinate space.

## Converting Source Annotations

We convert the selected publisher annotations with:

```bash
.venv/bin/python scripts/convert_evaluation_annotations.py
```

The command writes one COCO detection file for each dataset role and a separate
DLR person-count file below `data/evaluation/derived/annotations/`. These files
remain local because they are converted copies of external annotations. Their
locations are recorded in `manifest.csv`, and the conversion is reproducible
from the tracked scripts and original publisher downloads.

The conversion combines publisher annotations with the eight retained manual
CVAT annotations and produces:

| Role | Box-labelled images | Bounding boxes |
| --- | ---: | ---: |
| Training | 130 | 749 |
| Validation | 67 | 773 |
| Held-out test | 116 | 1,934 |

The 3,456 boxes include 1,255 people, 38 motorcycles, 2,115 cars or vans, ten
buses, and 38 trucks. DLR contributes 226,336 person points across 33
count-reference images. `manual_annotation_exports.csv` records the reviewed
CVAT archive and annotation JSON checksums, while the generated import report
records that 1,541 manual boxes from eight images were retained. Ten overlapping
boxes and three class corrections identified during the second visual pass are
recorded separately in
`manual_annotation_corrections.csv`; the original reviewed export remains
unchanged.

The present held-out boxes cover people, cars or vans, buses, and trucks.
Motorcycle boxes occur only in validation, while bicycles have no retained
support. We will report unsupported or low-support classes and will not make
persuasive per-class claims for them. The completed visual quality-control pass
is recorded separately from annotation preparation.

## Validation And Visual Review

We run the complete technical validation while annotation work is still in
progress with:

```bash
.venv/bin/python scripts/validate_evaluation_dataset.py --allow-incomplete
```

This command checks manifest fields, image readability, dimensions, SHA-256
hashes, duplicate images, source-group overlap, COCO membership and boxes, DLR
count references, and recorded quality-control decisions. It writes a structured
report to `data/evaluation/derived/reports/dataset_validation.json`.

During repeated local checks, we can omit the expensive file-hash pass:

```bash
.venv/bin/python scripts/validate_evaluation_dataset.py \
  --allow-incomplete \
  --skip-file-hashes
```

The strict final command has no `--allow-incomplete` option. The manual labels
are now imported, so it returns a failure only while required quality-control
decisions remain incomplete:

```bash
.venv/bin/python scripts/validate_evaluation_dataset.py
```

We render one review image for every manifest entry with:

```bash
.venv/bin/python scripts/render_evaluation_previews.py
```

The previews are stored below `data/evaluation/derived/previews/` and indexed by
`preview_index.csv`. Detection boxes are colour-coded by class, DLR person
points are shown in red, and reviewed manual images have their own index status.
The previews are inspection aids rather than new ground-truth data. The renderer
also writes a small candidate index and close-up images when two boxes overlap
by at least 80 percent. Same-class duplicate candidates and conflicting class
assignments are reported separately for visual confirmation.

For larger review batches, we generate labelled contact sheets containing only
assets that do not yet have a QC decision:

```bash
.venv/bin/python scripts/render_qc_contact_sheets.py
```

The generated index and sheets are stored below
`data/evaluation/derived/qc_contact_sheets/`. Contact sheets support the visual
scan, while uncertain examples are still opened at full resolution before a
decision is recorded. After every asset has a decision, we can regenerate sheets
for the complete dataset with `--include-reviewed`.

Second-pass decisions are recorded in `qc_reviews.csv`. A valid row identifies
the reviewer and date, uses `confirmed`, `corrected`, or `excluded`, and records
the number of changes. The current record contains 341 confirmed examples and
five corrected examples. The review used full-size overlays for warnings and
manual annotations, followed by labelled contact sheets for the remaining
publisher annotations and point masks. It was completed within the same
single-researcher workflow as preparation and is therefore not presented as an
independent annotation study.
