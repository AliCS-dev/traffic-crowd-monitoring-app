# Existing-Annotation Feasibility

**Follow-up, 10 October:** Ali approved the separate UAVDT adapter implementation.
The [adapter notes](uavdt_adapter.md) record the verified source exclusion rule,
conversion support and tests. The proposal below records the earlier decision
point; media verification and experiment freeze are still pending.

**7 October 2026, issue #113.** We inspected SDD annotation samples and UAVDT
metadata/ground truth without acquiring evaluation images or videos, running
inference, training a model or asking Ali to annotate. This follows the
[source inventory](source_inventory_v2.md) and his decision that a manual-review
campaign is not practical.

**Recommendation:** propose a separate, daytime UAVDT vehicle evaluation first.
Its existing annotations support car, truck and bus measurements, subject to
source-policy handling and media checks. SDD remains deferred. Neither source
establishes the original six-class, 40-independent-scene target, and the
[existing protocol](evaluation_v2_plan.md) has not been replaced.

## What We Could Access

| Source | Official access on this date | Inspection copy and boundaries |
| --- | --- | --- |
| SDD | The [publisher](https://cvgl.stanford.edu/projects/uav_data/) links a roughly 69 GB archive; its host timed out during our header request. We did not fetch it. | The [OpenTraj research copy](https://github.com/crowdbotp/OpenTraj/tree/97ec1d5e1b579f26febeaa9083705952deac338a/datasets/SDD) lists 60 annotation files, totaling 444,959,624 bytes. We inspected the smallest file in each of eight named scene folders: 14,340,090 bytes in total. This bandwidth-based sample is not a proposed evaluation sample. |
| UAVDT | The [publisher's toolkit and attribute links](https://sites.google.com/view/grli-uavdt/) returned a download warning and then quota-limit responses. We stopped retrying them. | The [pinned public mirror](https://huggingface.co/datasets/vanthanh/UAVDT-Benchmark-M/tree/ad1cfbe161c183cfdee26f6c42c6fff6552a54dc) supplied a 9,503-byte attribute ZIP. Byte-range requests retrieved the toolkit ZIP directory, its ground-truth section and README, rather than the full 245,719,325-byte toolkit. |

These are **mirror observations**, not authenticated copies of currently
accessible publisher archives. Pinned revisions and hashes establish which
bytes we inspected, not their correctness or agreement with the original
release. No original-publisher checksum comparison was possible.

SDD's publisher states CC BY-NC-SA 3.0; the mirror includes the same dataset
notice. We retain attribution to Robicquet et al., ECCV 2016. UAVDT's publisher
limits use to research and requests citation of Du et al., ECCV 2018. Its
toolkit README licenses library code under GNU GPL; that does not establish
general redistribution rights for dataset media. No source boxes, images or
videos are added to Git in this step.

## Measured UAVDT Coverage

The attribute archive contains **30 training and 20 test sequences** for this
DET/MOT release. The larger project description also covers other tasks; its
100-sequence headline must not be substituted for this archive's inventory.
The filter below requires `daylight=1`, `night=0`, `fog=0`. It is not a verified
rain-free filter or proof of independent physical locations.

| Annotation inventory | Daytime training | Daytime test |
| --- | ---: | ---: |
| Sequences | 17 | 12 |
| Distinct annotated frames, summed by sequence | 14,365 | 9,376 |
| Car box rows / positive sequences | 246,393 / 17 | 214,712 / 12 |
| Truck box rows / positive sequences | 14,125 / 15 | 2,449 / 7 |
| Bus box rows / positive sequences | 8,268 / 9 | 2,954 / 5 |
| Sequences with ignored-region rows | 14 | 10 |
| Bird-view flag present | 4 | 1 |

These are counts from source labels, **not accuracy results**. A box row is one
object annotation in one frame. For example, the daytime test rows correspond
to 14 truck track IDs and 10 bus track IDs when counted separately within
sequences. Repeated frames do not create new objects, and IDs cannot establish
identities across sequences. Five bus-positive sequences are not proof of five
independent sites. The single bird-view test sequence also falls short of the
original multi-group nadir target.

The test sequence IDs are `M0208`, `M0209`, `M0403`, `M0601`, `M0602`, `M0606`,
`M0801`, `M0802`, `M1301`, `M1302`, `M1303` and `M1401`. This list comes from
attributes, not from model performance. Published split roles remain intact;
training sequences do not become new official test sequences.

### Format And Integration Findings

The inspected toolkit README defines nine DET columns in `*_gt_whole.txt`:
frame, track ID, left, top, width, height, out-of-view, occlusion and category.
Native categories are **1=car, 2=truck, 3=bus**, not our canonical IDs.
`*_gt.txt` is MOT ground truth with different final-column meanings and must
not be parsed as DET annotations. `*_gt_ignore.txt` contains separate exclusions.

We parsed all 50 DET files and checked the ZIP CRC of all 150 GT members.
DET rows had the expected field counts, category/attribute codes, positive box
sizes and no duplicate frame/track pairs. Daytime DET frame IDs were contiguous
within their observed ranges. These checks do not verify video lengths, pixel
alignment, missing objects or semantic label accuracy. One attribute filename
contains a space (`M0701 _attr.txt`); the inspection trimmed this for joining
sequence IDs and retained the original member name in the evidence.

Out-of-view and occlusion codes are categorical, not ordered severities. For
example, the README uses occlusion `2` for large and `4` for small occlusion.
A converter must preserve their explicit meanings. We cannot discard ignore
rows or assume every source box is an ordinary positive evaluation target.

Our current [ground-truth type](../../evaluation/evaluation_data.py) has no
source-ignore-region representation, and the
[COCO metric conversion](../../evaluation/evaluation_metrics.py) emits ordinary
annotations with `iscrowd=0`. The current evaluation path therefore cannot
faithfully score this source without additional policy handling and tests.
This is an integration requirement, not an application-runtime failure.

## SDD Findings

The eight inspected files contained 343,957 rows. Of these, 201,049 have
`lost=0`, including 195,948 with `generated=1` (97.46 percent of non-lost rows).
The mirror's [format description](https://github.com/crowdbotp/OpenTraj/blob/97ec1d5e1b579f26febeaa9083705952deac338a/datasets/SDD/README.md)
identifies generated rows as interpolation. Interpolation is not automatically
an error, but these are not 201,049 independently drawn or reviewed boxes.

| Source class | Non-lost support in this small sample | Project compatibility |
| --- | --- | --- |
| Pedestrian | Present in all eight inspected files | Potential walking-person evidence, not an exhaustive all-person count |
| Biker | Present in seven | Not equivalent to a bicycle-only box; no automatic relabeling |
| Car | Present in two | Car/van policy still needs alignment |
| Bus | Present in two | Too little evidence here to infer full-source coverage |
| Skater, Cart | Present | Not project categories; excluded people/riders require a scoring policy |
| Motorcycle, Truck | Not source label categories | Cannot support those class claims |

Each sampled file had ten parseable columns, binary lost/occlusion/generated
flags, no duplicate frame/track pairs and no nonpositive non-lost boxes. Some
files begin at nonzero frame IDs. Annotation coordinates must be matched to the
correct original video and frame, not a resized preview or an assumed frame 0.
No pixels were inspected, no scene independence verified and no source split
for our detection task established. We defer SDD rather than turn these gaps
into a manual annotation task.

## Proposed Evaluation Procedure

This is a proposal for approval before implementation or experiments:

1. **Scope:** a separate UAVDT daytime car/truck/bus evaluation using existing
   publisher-provided labels obtained through a recorded source. It does not
   validate pedestrians, bicycles, motorcycles, dense crowds or the entire
   six-class application. Mirror provenance remains disclosed unless an
   original-copy comparison becomes possible.
2. **Partitions:** preserve training/test membership. Any tuning uses only
   training-side data with an explicitly recorded validation division. We
   reserve the 12 attribute-selected test sequences for the final comparison;
   they are not development smoke fixtures. Physical-location overlap and
   unknown model pretraining exposure remain limitations, not assumed absent.
3. **Media and labels:** verify matching sequence/frame files, dimensions and
   hashes before freezing the selection. A full mirrored media archive is
   listed as 6,790,452,113 bytes (about 6.79 GB); selective media retrieval has
   not been tested. No media download is approved by this report. Missing media
   or unclear labels cannot silently become negative examples.
4. **Scoring:** add tested handling of ignored areas, source attributes, class
   IDs and coordinates before inference. Define the model's car/van-to-source-
   car mapping explicitly as an alignment assumption. Exclude unsupported
   prediction classes from this source-specific comparison, not from historical
   results. Verify behavior against source evaluation rules; any deliberate
   difference is documented rather than called an official benchmark score.
5. **Outputs:** propose per-class precision/recall, AP50 and AP50-95, plus MAE
   and NAE for the annotated car/truck/bus total using the same declared
   exclusions. Include per-sequence results and measured runtime. This is a
   daytime subset evaluation, not the full official challenge score or a
   unique-vehicle traffic-flow measurement. Frame counts are not independent
   sample counts; do not use an IID-frame uncertainty claim.
6. **Freeze and claims:** agree the protocol, thresholds, frame-selection rule
   and baseline/candidate comparison before test predictions. Any spatial
   overlap discovered in media checks is recorded before freezing. This report
   neither lowers existing pass thresholds nor declares a new pass. It does
   not promote these sequences to a verified independent-location holdout.

The next implementation, if approved, is the bounded UAVDT annotation adapter
and ignore-aware evaluation support with tests. Model training and SDD
integration are separate decisions. The original custom-dataset campaign stays
on hold; Ali is not assigned annotation work.

## Evidence And Method

The [machine-readable inspection record](../../data/evaluation/annotation_feasibility_v2.json)
contains all eight SDD file hashes, their Git blob IDs, all 50 UAVDT sequence
summaries, native class/attribute definitions and hashes of inspected members.
It is inventory evidence, not a dataset manifest or model-metric report.

We used Python's CSV and ZIP readers for an offline inspection. SDD counts use
space-separated rows, source labels and `lost=0`; generated and occluded flags
are counted separately. UAVDT counts use the nine-column DET files joined to
the ten binary sequence attributes. Class-positive sequence counts count
nonzero support, not independent locations. Hashes cover the exact downloaded
bytes. Git blob hashes matched the pinned SDD listing; UAVDT ZIP reads passed
internal CRC checks. Neither check proves annotation correctness.

The UAVDT toolkit byte ranges were `43228793-50845700` for the GT section and
README and `245574921-245719324` for the ZIP directory. A separate initial
65,536-byte directory probe was also fetched. The record distinguishes the
mirror-advertised full-archive SHA-256 from locally measured range/member
hashes: we did not download or hash the full toolkit. Raw files remain outside
Git; the pinned links identify the inspected copies for later reproduction.

The [historical results](results_index.md) remain unchanged, including the
failed quality gate and unsupported dense-crowd state. Issue #113 remains open.
