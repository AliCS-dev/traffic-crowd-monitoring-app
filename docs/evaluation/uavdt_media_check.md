# UAVDT Media Compatibility Check

**13 October 2026, issue #113.** We retrieved nine training images, converted
their existing labels and inspected every resulting overlay. The downloader,
frame lookup and annotation adapter work together on real data. **This is not
an accuracy evaluation or a declaration that the dataset is ready.**

The [machine-readable record](../../data/evaluation/uavdt_media_check.json)
contains exact members, hashes, dimensions, class counts, geometry flags,
source-file hashes and HTTP range evidence. We ran no detector, changed no
source labels and downloaded no test images. The observations below are an
assistant-assisted visual inspection, not independent human annotation review
or approval by Ali.

## Selection And Access

Before opening images, we selected `M0101`, `M0210` and `M0702` from the published
training split. Their recorded attributes and label inventories provide
front/side and bird views, car/truck/bus examples and both empty and nonempty
ignore files. We selected the first, middle and last labelled frame of each
sequence. This deliberately small compatibility selection is neither random nor
representative and must not become a final holdout.

We used the same [pinned mirror](https://huggingface.co/datasets/vanthanh/UAVDT-Benchmark-M/tree/ad1cfbe161c183cfdee26f6c42c6fff6552a54dc)
as the earlier annotation inspection. The script retrieved **7,547,834 bytes**:
466,937 toolkit bytes and 7,080,897 media-archive bytes. This includes ZIP
directories, headers and selected payloads, not the complete 6.79 GB archive.
A separate initial access probe fetched 65,536 bytes, bringing the successful
payload total for this session to 7,613,370 bytes, excluding HTTP headers.

Every request required an exact HTTP 206 byte range. Python's standard ZIP
reader checked member CRCs; SHA-256 hashes identify downloaded images and labels.
Selected label/attribute hashes match the retained October 7 inspection.
None of these checks proves agreement with the publisher's original copy.

The [publisher](https://sites.google.com/view/grli-uavdt/) restricts the dataset
to research and requests citation of Du et al., *The Unmanned Aerial Vehicle
Benchmark: Object Detection and Tracking*, ECCV 2018. Images, native labels and
overlays remain in ignored local storage; we have not assumed permission to
republish them in Git. Reproduction/publication permissions still need checking
before including source images in a publicly distributed thesis.

## Measured Sample

All nine decoded images are **1024 x 540**, not the 1080 x 540 stated in the
publisher's general description. We use actual decoded dimensions and preserve
source coordinates without resizing. No global shift or scale mismatch was
apparent in these overlays; that does not authenticate the mirror or establish
pixel-perfect accuracy for every box.

| Sequence / frame | Car or van | Truck | Bus | Ignore rectangles |
| --- | ---: | ---: | ---: | ---: |
| M0101 / 1 | 13 | 1 | 1 | 3 |
| M0101 / 204 | 13 | 0 | 0 | 2 |
| M0101 / 407 | 9 | 0 | 0 | 1 |
| M0210 / 1 | 4 | 2 | 0 | 0 |
| M0210 / 292 | 7 | 4 | 0 | 0 |
| M0210 / 583 | 15 | 5 | 0 | 0 |
| M0702 / 1 | 36 | 1 | 3 | 3 |
| M0702 / 389 | 58 | 0 | 6 | 1 |
| M0702 / 777 | 51 | 2 | 4 | 3 |
| **Total box rows** | **206** | **15** | **14** | **13** |

There are 235 labelled object instances across nine frames, not 235 distinct
vehicles. All selected image hashes differ. This only excludes exact-file
duplicates, not near-duplicates or repeated locations. Three frames from one
sequence are correlated, and three sequence IDs do not prove three independent
capture locations.

Automated checks found no out-of-bounds boxes, no same-class duplicate or
cross-class conflict pairs at the existing 0.8 IoU check threshold, and no
labelled box strictly contained by an ignore rectangle. Six boxes touch an image
edge. These technical checks did **not** detect the semantic concerns below.

## Visual Observations

- **M0101, all three frames:** most supplied boxes align with road vehicles.
  Frame 1 includes a visibly identifiable coach and a small truck. Ignore regions
  cover parked-vehicle areas and change with the camera view. Pedestrians and
  two-wheelers are visible but outside this three-class label scope.
- **M0210, frames 1 and 292:** the toll-plaza view changes with camera movement;
  the supplied car/truck boxes generally follow visible vehicles. Shadows and
  the toll canopy limit what can be independently identified from a still image.
- **M0210, frame 583:** track 34 has a native car box `(1, 0, 104, 230)` spanning
  vegetation and road without an obvious matching vehicle. Track 18 has a box
  `(500, 345, 34, 19)` over the toll canopy; its target is not visually identifiable
  in the image. Both source records have occlusion code 1 (none). These are
  unresolved source-label/visibility concerns, not corrected annotations. The
  same coordinates occur in the downloaded native DET file, whose hash matches
  the earlier inspection, so the converter has not introduced these boxes.
- **M0702, all three frames:** cars and buses broadly align in the dense
  intersection view. Several vehicles are partially occluded or cross image
  boundaries. Ignore regions cover groups of parked vehicles. This confirms the
  need for source-specific exclusions; the resulting count is not a count of
  every visible vehicle in the whole photograph.

All nine frames and both questioned records remain in the inspection evidence.
We have not silently dropped difficult examples, repaired boxes, marked labels
as human-reviewed or selected data using model performance.

## Local Artifacts And Reproduction

Local images, native labels, the inspection-only training manifest, canonical
annotations, report and nine PNG overlays are under:

```text
data/evaluation/raw/uavdt_media_check_20261013/
```

The `overlays/` filenames include sequence and frame. Original images remain
unchanged; overlays retain native image dimensions with a separate legend below.
Blue boxes are cars/vans, yellow trucks, purple buses and thick magenta rectangles
ignored areas. The raw directory is intentionally absent from GitHub.

Reproduction uses the retained attribute ZIP and inspection record, plus network
access to the pinned toolkit/media archives:

```bash
.venv/bin/python scripts/check_uavdt_media.py
```

The command refuses an existing output directory. A repeat run uses an explicit
new directory via `--output-directory data/evaluation/raw/uavdt_media_check_repeat`.
The script caps toolkit/media downloads at 8/24 MB and individual archive members
at 2 MB. It never falls back to a full archive download. Checksummed metadata is
committed separately; restricted images and overlays are not copied into Git.

## Outcome And Next Step

Verification passed with **512 Python tests**, with 11 opt-in database tests
skipped locally. This includes 18 focused range-reader/media-check tests. Lint,
formatting, Python compilation and installed dependency checks passed.

**Technical integration: passed for these nine frames. Source-label readiness:
not yet established.** The inspection reveals why structural validation alone
cannot establish trustworthy ground truth. No model-accuracy result, six-class
coverage improvement or new quality-gate pass follows from this work.

Next we need to resolve or explicitly document the two questioned source records
and the occlusion policy, then freeze the source-specific sampling and experiment
settings. Any label exclusion or correction must be declared before predictions,
with an audit trail, not chosen to improve a model score. This does not require
Ali to start a new annotation campaign. Test sequences stay reserved, the
historical failed gate stays unchanged, and issue #113 remains in progress.
