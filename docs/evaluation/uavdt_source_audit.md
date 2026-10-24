# UAVDT Publisher Source Check

[Results index](results_index.md) | [Prediction review](uavdt_error_review.md)

**24 October 2026, issue #113.** We compared our frozen UAVDT inputs with
files downloaded directly from the links on the
[publisher's project page](https://sites.google.com/view/grli-uavdt/).
The [compact evidence record](../../data/evaluation/uavdt_source_audit.json)
contains member names, hashes, transfer counts and the exact scope.

## Conclusion

**The checked files match the publisher release.** All 34 detection/ignore
annotation files used by our 17 baseline sequences match byte for byte. So do
all 20 selected images from M0207 and M0402, under the same sequence and frame
filenames. This rules out a different mirror copy or local filename pairing
for these examples, but does not certify the publisher's labels.

The sparse M0207 labels and questioned M0402 categories are present in the
publisher-hosted files too. We found no conversion error that explains those
observations, and made no changes to the dataset or model.

## What Was Compared

| Check | Result |
| --- | --- |
| Toolkit ZIP directory and recorded ground-truth/README range | Both match the recorded mirror hashes |
| Publisher toolkit README | Matches the previously inspected README |
| Native DET and ignore files for the 17 baseline sequences | 34 of 34 equal to the local frozen files |
| Selected M0207 images | 10 of 10 equal to local bytes |
| Selected M0402 images | 10 of 10 equal to local bytes |
| DET versus MOT frame/track/box fields in M0207 and M0402 | Identical within each sequence |
| Frozen dataset readiness and canonical conversion | Still agree with the completed baseline |

We used the publisher-linked
[DET/MOT toolkit](https://drive.google.com/file/d/19498uJd7T9w4quwnQEy62nibt3uyT9pq/view)
and [image archive](https://drive.google.com/file/d/1m8KA6oPIRK_Iwt9TYFquC87vBc_8wRVc/view).
Unlike the earlier quota-limited attempts, bounded downloads worked today.
The successful audit read 7,761,312 toolkit bytes and 9,405,009 image-archive
bytes, about 17.2 MB in total. These figures exclude preliminary access probes,
HTTP headers and redirects. No complete archive was downloaded.

The toolkit ranges also contain metadata and annotations beyond the selected
sequences; we checked range equality, not new test-set performance or visual
quality. Only the 20 selected training-image members were read from the image
archive. No test pixels, new predictions or model weights were downloaded.

We did **not** compare the remaining 150 baseline images or the separate
attribute archive with the publisher. Whole-archive SHA-256 equality is not
claimed. Older protocol and provenance flags remain historical records of
what was known when the baseline ran; this report adds narrower, dated evidence.

## File Format and Pairing

The publisher toolkit README distinguishes the nine-column detection file
`*_gt_whole.txt` from the tracking file `*_gt.txt`. Detection fields carry
out-of-view, occlusion and category codes after the frame/track/box fields;
tracking fields have different meanings. Detection categories are car `1`,
truck `2` and bus `3`. Our adapter uses that mapping, preserving source box
coordinates and attributes. Overlay colours are a separate display concern,
corrected in the previous review.

The publisher describes detection as a three-class vehicle task, with
occlusion and out-of-view attributes. It excludes objects more than halfway
out of view and discusses very small vehicles and ignored regions. Those
rules alone do not explain the substantial visible unlabelled vehicles in
our M0207 review; we cannot infer an undocumented exception from them.
[Publisher task description](https://sites.google.com/view/grli-uavdt/)

| Native sequence | DET rows | Track IDs | Native categories | DET/MOT geometry |
| --- | ---: | ---: | --- | --- |
| M0207 | 1,062 | 3 | 491 car rows, 571 bus rows | Equal |
| M0402 | 10,210 | 45 | All rows are car | Equal |

These are full native sequence inventories, not counts from our selected
frames or independent vehicles across scenes. M0207's ignore file is empty.
Using its MOT file would not add missing reference boxes: the same frame IDs,
track IDs and coordinates appear there. M0402's questioned tracks retain the
car category in the publisher DET file.

Matching image bytes under publisher filenames verifies our acquisition and
local pairing. It cannot rule out an upstream annotation mistake or certify
the visual identity of every box.

## Independent Context

Song and Lee's **SFTrack** study reports UAVDT annotation omissions and boxes
persisting outside an object's visible interval. Their refinement covers
4,721 frames and adds 43,981 annotation instances and 55 tracks. This shows
that source annotation problems have been reported independently; it does not
prove that they corrected our two sequences.
[SFTrack, sections IV-A and IV-B](https://arxiv.org/html/2410.20079v1#S4)

That study concerns multi-object tracking. Its refined annotations are not
automatically a replacement for our three-class detection reference. We have
not verified their class coverage, split, permissions or correspondence to
our selected images, and did not download or adopt them in this step.

## Thesis Decision

The baseline remains useful as a reproducible comparison with native source
labels. It is not a reliable stand-alone estimate of complete scene counts
in the questioned sequence, nor proof that every class disagreement comes
from the detector. The duplicate prediction and other model limitations
from the previous review remain concerns.

We will not remove difficult sequences, replace labels with predictions or
raise thresholds simply to make these scores look better. Any correction
would need an independently justified, versioned reference and a new result.
The historical failed quality gate and unsupported dense-crowd status remain
unchanged; this source check does not improve model accuracy.

**Next decision:** retain this UAVDT run as development evidence with explicit
limitations. Before using another experiment to choose a model, establish a
task-compatible reference with independently checked labels. If that cannot
be obtained within the thesis scope, retain the limitation and narrow the
accuracy claims rather than start another annotation campaign or imply that
software tests certify detection quality. Issue #113 stays open.

## Reproduction

From the repository root, with the prepared local baseline inputs available:

```bash
.venv/bin/python scripts/audit_uavdt_sources.py
```

This needs network access, but not Docker or a GPU. It reuses the bounded ZIP
reader and frozen readiness checks. Per-run payload budgets are 9 MB for the
toolkit and 24 MB for images; an unexpected response, size or member mismatch
stops verification. It never writes into the prepared dataset or executes
downloaded code.

The completed local record is under
`data/evaluation/derived/uavdt_source_audit/20261024T092117Z-publisher-comparison/`.
It contains `audit.json` and `download_attempt.json`, including successful
range hashes. Failed runs retain transfer logs but receive no success report.
The tracked compact record adds the clean audit commit and source links.
It contains no images or bounding-box coordinates.

Local verification passed with **570 Python tests**, with 11 opt-in database
tests skipped, plus lint and formatting. Twelve new tests cover comparisons,
task fields, training-only selection, input preservation and failure handling.
