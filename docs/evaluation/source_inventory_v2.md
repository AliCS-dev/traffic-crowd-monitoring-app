# Evaluation V2 Source Inventory

**Research date: 4 October 2026.** This is the source-feasibility step of #113,
not an acquired dataset or a frozen evaluation protocol. We reviewed publisher
pages, papers, annotation documentation and the pinned baseline model card.
We downloaded no new media or annotation archives, counted no new boxes and
changed no historical labels, splits, weights or results.

The [v2 plan](evaluation_v2_plan.md) defines our agreed daytime, six-class scope
and provisional 400-image, 40-scene-group target. The source review has **not
established that this target or its proposed class floors can be met** within
an acceptable review workload. Published clip counts are not independent scene
counts. A source with suitable labels is not automatically an independent test
source for a model trained on it.

**Workload decision:** after reviewing the estimates below, Ali said he cannot
take on the proposed annotation-review work. We will not plan a manual
annotation campaign or assume a review budget. The custom 400-image proposal
is on hold pending an explicitly agreed alternative; its targets have not
been silently reduced or declared satisfied.

## Shortlist

The table describes source labels, not verified counts of usable v2 objects.
Mappings remain subject to our [annotation policy](annotation_guide.md).

| Source | Potential class coverage | Scene evidence | Proposed role |
| --- | --- | --- | --- |
| VisDrone | All six; rider/person conventions need review | Multiple cities, but eligible groups not audited | Conditional development source or separate official benchmark; not our new final holdout |
| Stanford Drone Dataset (SDD) | Person, bicycle, car and bus; rider boxes need review | Eight named campus scenes, not 60 independent video locations | Priority metadata check for person/bicycle coverage |
| UAVDT | Car, bus and truck only | 100 sequences; independent locations not established | Priority metadata check for vehicle coverage |
| AU-AIR | All six, plus trailer outside our taxonomy | Eight videos at one intersection | At most one supplementary scene group; access and terms unresolved |
| Traffic Images Captured from UAVs | Car and motorcycle only | Scene descriptions available; repeats need grouping | Check genuinely new locations before further use |
| New Wikimedia Commons files | No supplied evaluation labels in the leads below | Per-file location and camera evidence | Deferred: would require manual annotation and review |

These are candidates, not an approved acquisition list. For partial-label
sources, an absent class annotation is not evidence that the object is absent.
Every core image needs a full six-class review. Published benchmark results
retain their native scope and remain separate from our custom application test.

## Evidence And Restrictions

### VisDrone

The official [dataset repository](https://github.com/VisDrone/VisDrone-Dataset)
and [detection task](https://aiskyeye.com/object-detection_2024/) describe aerial
data and labels including pedestrians, bicycles, motorcycles, cars, vans, buses
and trucks. We would combine car/van, while checking the separate pedestrian,
people and rider conventions. We have not audited locations per class.

The [annotation specification](https://github.com/VisDrone/VisDrone2018-DET-toolkit)
includes ignore flags, truncation and occlusion; the [official FAQ](https://aiskyeye.com/faq/)
explains ignored regions. Our canonical conversion must preserve an explicit
scoring policy before these images can support comparable metrics.

The [download page](https://aiskyeye.com/download/) offers the dataset and asks
for citation, but we did not verify an explicit dataset licence or redistribution
grant on the reviewed pages. The toolkit's research-use terms are not a dataset
licence. Terms need confirmation before new acquisition; we cannot infer them
from mirrors or the model's licence.

Our [pinned model card](https://huggingface.co/dronefreak/visdrone-yolov26m/blob/20879fa2d2f351d1e032bfd0a38a5a6b735b0f03/README.md)
states VisDrone fine-tuning and already reports VisDrone evaluation. It does not
provide an image-level training manifest. We therefore exclude this collection
from the proposed fresh holdout for that baseline, without claiming every
official test image was used for training. Official split roles remain intact.

### Stanford Drone Dataset

The [publisher page](https://cvgl.stanford.edu/projects/uav_data/) lists eight
campus scenes across 60 videos and labels for pedestrians, bicyclists, cars,
buses, skateboarders and carts. There are no dedicated motorcycle or truck
labels. Bicyclist boxes cannot automatically become bicycle-only boxes; rider
extent and missing people need inspection.

The page explicitly states **CC BY-NC-SA 3.0** and requests citation of
Robicquet et al., ECCV 2016. Attribution, noncommercial use and share-alike
conditions need to accompany any permitted shared adaptations. We would retain
the original terms with the acquisition record, not relicense source assets
under our application licence.

Our grouping rule gives at most eight named scene groups before checking nearby
or overlapping locations. The publisher links a roughly 69 GB download; we have
not verified archive availability or selective retrieval. Annotation metadata
comes first. This is a potential person/bicycle contribution, not proof of the
bus quota, six-class completeness or cross-city generalization.

### UAVDT

The [official project page](https://sites.google.com/view/grli-uavdt/) describes
100 UAV sequences, car/truck/bus annotations, ignore areas and attributes for
conditions and camera views. Daytime filtering is necessary; 100 sequences do
not establish 100 different physical scenes. People, bicycles and motorcycles
would need additional review and annotation for our core dataset.

The publisher restricts the benchmark to **research purposes** and requests
citation of Du et al., ECCV 2018. We did not verify a general redistribution
grant. Linked data, attributes and toolkit archives were not downloaded or
validated. We propose inspecting metadata for location grouping, class support
and ignore-region handling before considering media acquisition. No reviewed
model record establishes UAVDT exposure, but unknown exposure is not proof of
independence.

### AU-AIR

The [original paper, section III-B](https://arxiv.org/html/2001.11737v1)
describes eight videos at the intersection of Skejby Nordlandsvej and
P. O. Pedersensvej in Aarhus. Its person, car, van, truck, motorbike, bike and bus
labels potentially map to all six classes; trailer needs a separate exclusion
policy. GPS and camera information could support provenance checks.

Under our rules this is **one scene group**, allowing at most ten core images,
not eight independent groups. It cannot by itself provide the required
validation/holdout class diversity. The [original dataset site](https://bozcani.github.io/auairdataset/)
returned HTTP 404 during this review. We could not verify current download
access or authoritative dataset terms; secondary copies are not permission
evidence. We defer acquisition pending recovery of those records.

### Traffic Images Captured From UAVs

The [Zenodo record](https://zenodo.org/records/5776219) provides car/motorcycle
annotations, 12 archives and several road/roundabout scene descriptions. Its
[record metadata](https://zenodo.org/api/records/5776219) identifies **CC BY 4.0**.
We retain attribution to Sergio Ghisler, Javier Sanchez-Soriano and Sergio
Bemposta Rosende, the record DOI, licence and a description of modifications.

Our [historical audit](dataset_audit_v1.md) already records three archives from
two scenes. More clips of these locations cannot become a fresh holdout.
Unseen road locations are potential additions only after comparison; near/far
roundabout descriptions are not evidence of independent sites. The missing
four classes still require review. We have not counted eligible new groups or
downloaded further archives.

### Wikimedia Commons

The [Commons reuse guidance](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/en)
requires checking the individual file's terms. We retain author, original
source, capture/location evidence, licence, page revision and modifications for
each selected item. Existing Jane Byrne and Renai scenes remain historical or
development data, including other frames of those scenes.

The following concrete leads show both possibilities and unresolved checks;
none has been acquired, annotated or admitted to v2:

| File | Evidence on the file page | Remaining check |
| --- | --- | --- |
| [Drone view of roundabout](https://commons.wikimedia.org/wiki/File:Drone_view_of_roundabout_%28Unsplash%29.jpg) | Enrapture Media, 24 May 2017; 5,226 x 2,936; CC0 notice for pre-June-2017 Unsplash publication; DJI camera metadata and coordinates 49.458787, -2.534420 | Retain archived publication/licence evidence; compare location with existing sources; inspect full-resolution class visibility. One image is not a multi-scene dataset. |
| [Roundabout 14 61](https://commons.wikimedia.org/wiki/File:Roundabout_14_61.webm) | Wikideas1, 8 September 2023; La Crosse; CC0; 36 seconds at 1,920 x 1,080 | The reviewed page does not establish a drone platform. Confirm camera provenance and usable daytime targets before considering sampling. |
| [Drone 3-27-2025 1A](https://commons.wikimedia.org/wiki/File:Drone_3-27-2025_1A.webm) | Wheeler Cowperthwaite; Providence category; stated CC BY 2.0, imported from Flickr | Commons marks the external licence as not yet reviewed. Verify the original source and exact location; traffic suitability has not been checked. Defer selection. |

Copyright terms do not settle all privacy or other rights. Licence summaries
here are acquisition notes, not a blanket clearance to publish every image in
the repository or thesis. Media and labels retain their own terms.

## Sources We Would Not Prioritize

- [DroneVehicle](https://github.com/VisDrone/DroneVehicle) uses paired RGB/IR
  imagery and oriented boxes for car, truck, bus, van and freight car. It lacks
  our three non-car road-user label categories. Border offsets and rotated-box
  conversion add work, and we did not verify explicit dataset terms. We defer
  it rather than adding another annotation format to this step.
- [SODA-A](https://shaunyuan22.github.io/SODA/) states CC BY-NC 4.0, but its
  [official class definitions](https://github.com/shaunyuan22/SODA-mmrotate/blob/main/mmrotate/datasets/sodaa.py)
  use small/large vehicle categories among other objects. They do not provide
  our six road-user classes. Converting vehicle size into car/bus/truck labels
  would invent information. We defer it for this evaluation.

## Feasibility And Review Effort

The limiting factors are independent locations, bus/bicycle/motorcycle support
across groups, and complete labels, not the number of available video frames.
No source above yet has a verified v2 per-class group-count table. In
particular, the proposed five positive groups per class in each evaluation
partition remain unproven. We also lack measured negative-image, small-object,
occlusion and nadir/oblique coverage. Unknown values do not satisfy quotas.

These are **planning assumptions, not measured annotation timings**:

| Work per image | Assumed review and correction time |
| --- | ---: |
| Existing boxes with a compatible class policy | 3-6 minutes |
| Partial labels, including finding and adding missing classes | 6-12 minutes |
| Manual boxes from scratch in a moderately populated image | 10-20 minutes |

The allowances include a second visual pass but exclude permission enquiries,
download delays and adapter development. Dense scenes with hundreds of objects
can take much longer. Existing labels still need human review; automated
conversion is not approval of ground truth.

For illustration only, 240 compatible-label images, 80 partial-label images
and 80 unlabelled images would require about **33-67 hours** of review, plus
an assumed **4-8 hours** for provenance and organization: roughly **37-75
hours** overall, before adapter work. This mix is not an available or selected
dataset. Even 400 compatible-label images imply roughly 20-40 review hours
under these assumptions. Ali cannot take on this work, so these estimates
explain why we are not proceeding with that campaign. We do not record reviews
in his name that he has not performed.

## Recommended Next Step

We propose one bounded metadata check of **SDD and UAVDT**, with no training,
bulk media download or manual annotation. The aim is now to establish what we
can evaluate using existing publisher-provided ground truth, not to assemble
400 newly reviewed images. Commons acquisition is deferred because the leads
need labels we do not have the capacity to produce.

A possible alternative is separate source-specific benchmarks, retaining each
source's label conventions and official split roles. We would report only
supported classes and keep their scores separate. This is a proposal for Ali's
approval, not a replacement already applied to the six-class protocol. It
would not establish a new custom independent holdout or satisfy the original
scene/class floors merely by combining datasets.

The next deliverable would contain:

1. Accessible annotation/attribute file listings, exact release identifiers
   and retained permission evidence. Any metadata download is identified and
   size-checked first; an unavailable link does not trigger a full media fetch.
2. A class-compatibility and location-group table distinguishing existing
   usable labels, unresolved grouping and classes requiring manual changes.
   The latter are not used for new accuracy claims. Official split roles and
   historical/model overlap remain visible.
3. A concrete proposal using existing annotations, with download sizes,
   automatable conversion/validation checks and explicit unsupported claims.
   Any change to the custom dataset, independence claims or success criteria
   comes back for approval before experiments. An unsuitable source is
   rejected, not turned into an unplanned manual annotation task.

Automated checks can test file integrity, coordinates, category mapping,
duplicates and split consistency. They cannot prove exhaustive annotation or
correct semantic labels. Source-provided ground truth is identified as such,
with the publisher's quality evidence and our lack of independent visual
review disclosed. We do not present automated checks or model predictions as
human annotation approval.

An eventual acquisition record needs source release and item IDs, original
labels, mapping/ignore policy, author and licence evidence, location/capture
group, known model exposure, proposed role and reviewer status. Downloaded
media and annotations then receive measured SHA-256 checksums. None of those
per-file records is fabricated from this website review.

## What This Changes

We now have a shortlist, explicit reasons to defer unsuitable sources and an
honest workload estimate. The [historical quality gate](final_quality_gate.md)
is unchanged, and dense-crowd analysis remains unsupported. This report is
planning evidence for the thesis methodology, not a new accuracy measurement.
Issue #113 remains open for approved acquisition, review, splitting and a
versioned dataset release.
