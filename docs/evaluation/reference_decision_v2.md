# Evaluation Reference Decision

**25 October 2026, issue #113.** We are prioritizing completion of the
application and deferring new model-selection experiments. Ali approved this
direction after reviewing the reference-data constraints. We have not passed
the model quality gate, completed the proposed v2 dataset, or adopted new labels.

## Decision

We retain the current experimental detector and its visible limitations. The
UAVDT run remains a development comparison with source-provided labels, not a
complete-scene counting reference or an independent final evaluation. Historical
results and the unsupported dense-crowd decision remain unchanged.

We stop this source search here. None of the options inspected in this review
is ready to supply the agreed six-class reference without additional work that
we have not resourced. This is a decision about our inspected sources and
available review capacity, not a claim that no suitable dataset exists.

Issues #113, #114 and #115 remain open and deferred. Their unmet acceptance
criteria are not checked off or replaced with easier thresholds. We will not
train, select another detector, or open a final test for model selection under
this decision. There is no new annotation assignment for Ali.

The next implementation task is #116, the scene-first analysis workspace.
We can write the stable architecture sections under #81 alongside that work.
After the interface and release scope are fixed, #26 and #79 cover the final
test gate and system evaluation. Optional video-navigation work under #117
remains a separate scope decision, not a prerequisite added by this review.

## Why We Are Not Replacing the Reference

| Option | What the evidence supports | Decision for this thesis |
| --- | --- | --- |
| Native UAVDT labels | The [publisher comparison](uavdt_source_audit.md) confirms the checked source identities; it does not resolve annotation omissions or class concerns. | Keep the existing development result and limitations. Do not tune against the questioned labels to obtain a passing score. |
| SFTrack refined UAVDT | The authors release test-set tracking annotations. The inspected archive contains no M0207 or M0402 replacement, and their UAVDT configuration has one class. | Not a drop-in replacement for the three-class development reference or six-class v2 dataset. |
| Stanford Drone Dataset | The publisher lists eight scenes with pedestrian, bicyclist, car, bus, cart and skateboarder labels. Motorcycle/truck support and rider-box compatibility do not meet our six-class policy. | Retain the [earlier inspection](annotation_feasibility_v2.md); no new adapter or manual relabeling campaign. |
| VisDrone | The current model was fine-tuned on this collection. Its published model card also reports VisDrone evaluation. | An official benchmark can have a legitimate separate role, but we do not present it as a newly independent source for this model or as our custom six-class holdout. |

The [SDD publisher page](https://cvgl.stanford.edu/projects/uav_data/) and
[model card](https://huggingface.co/dronefreak/visdrone-yolov26m) support those
source-specific statements. We have not established image-level training
overlap for every VisDrone split. The broader alternatives and permission gaps
remain in the [source inventory](source_inventory_v2.md); we did not start a
new search across additional collections today.

## Refined UAVDT Inspection

We followed the download from the
[authors' project page](https://songinpyo.github.io/SFTrack-Project/).
Their [paper, sections IV-A and IV-B](https://arxiv.org/html/2410.20079v1#S4)
describes the tracking task and annotation corrections. The
[pinned UAVDT experiment configuration](https://github.com/Songinpyo/SFTrack/blob/2a70c13c4c09736fca4f224936bbcf68633ceaf2/exps/example/mot/yolox_x_uavdt.py)
sets `num_classes = 1`. We read that code; we did not execute it or use its model.

The [downloaded annotation archive](https://songinpyo.github.io/SFTrack-Project/static/files/UAVDT_Refined_Annotations_SFTrack.zip)
is 2,376,655 bytes. Its measured SHA-256 is
`d03c1cdff26a3e1b285ca048f21eeb61b0c6729f4d678b3a4b8f57d8aad933fe`.
Our [inspection record](../../data/evaluation/sftrack_reference_inspection.json)
retains member hashes, source-split matches and counts without boxes or images.

- All 20 annotation filenames match test sequences in our earlier source
  inventory. Neither questioned training sequence, M0207 nor M0402, is present.
- The files contain 384,887 rows, matching the archive README's total. Each
  parsed row has nine fields. Columns 7 and 8 are always `1`; column 9 is
  `-1` or `1.0`. These observations are not the three-class DET mapping.
- ZIP CRC checks passed. We used Python's `zipfile` and CSV parser, checked all
  supplied annotation rows, and matched sequence IDs to the hashed October 7
  inventory. These are format and provenance checks, not visual label approval.
- The archive README requests citation but does not state an explicit
  annotation redistribution licence. The website's CC BY-SA notice is not
  treated as permission to relicense UAVDT data. No source files are committed.

The archive remains locally under
`data/evaluation/raw/reference_decision_20261025/`, which Git ignores. Download
size was capped at 3 MiB; inspection allowed at most 100 members and 32 MB of
uncompressed content. We read files in memory without extracting archive paths.
No evaluation media, predictions, weights or original labels were changed.

This step accessed **test annotation metadata and rows**, not test images or
model outputs. A later study must retain that access history; these files have
not been admitted to an untouched custom holdout. A separate single-class
tracking or detection study might use this release after checking its task
policy, permissions and model exposure. We are not starting that study here.

## What We Can Claim

We can describe and measure an application that processes images and sampled
video frames, persists results, displays spatial counts, and records experimental
threshold events. The current model's measured accuracy and failure cases belong
alongside those system results, not hidden behind successful software tests.

We cannot claim reliable six-class aerial detection, validated dense-crowd
counting, state-of-the-art accuracy, or safety-critical monitoring. New UI
features must retain the experimental status and unsupported crowd count.
Functional tests do not turn an uncertain detection into a verified object.

This decision changes the remaining work order, not the accepted thesis title
or abstract. Any formal revision of university research objectives belongs in
a discussion with the supervisor; this report does not establish acceptance.

## Reopening Accuracy Work

We would reopen model selection only with a task-compatible reference, a
documented review basis and permission record, a feasible review budget, and
separate development/final-test roles. Model exposure and scene overlap must
be addressed or explicitly limit the claims. The experiment and stopping rules
would be agreed before new predictions. A benchmark name or automated integrity
check alone does not satisfy those conditions.

## Verification

We reproduced the receipt's archive, README, split-inventory and 20 member
hashes, row counts, field counts and source-split matches. All 91 checked local
documentation links resolve. The Python suite passed 570 tests, with 11 opt-in
database tests skipped locally. No application code changed; these checks do
not certify the source labels or provide a new detector-accuracy result.
