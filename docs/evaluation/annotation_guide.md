# Aerial Evaluation Annotation Guide

## Purpose

This guide defines how we prepare ground truth for the aerial detection quality
gate. We use the same rules across collections so that model errors reflect the
model as far as possible, rather than inconsistent labels.

The guide is fixed before model benchmarking begins. A later correction that
changes labels or dataset membership must be recorded with a new dataset
version, followed by a rerun of every affected result.

## Annotation Tool And Format

We use CVAT for visual review and manual correction. CVAT provides image and
video annotation, review workflows, and COCO export without tying the dataset to
one detector implementation.

COCO detection JSON is the canonical bounding-box format. It supports the
established COCO evaluation API required by our evaluation protocol and keeps
pixel coordinates, image dimensions, categories, and optional annotation flags
in one structured file. Source annotations may use YOLO or collection-specific
formats, but conversion into the canonical format is automated and validated.

DLR-ACD remains a count-only dataset because it provides person points rather
than bounding boxes. Its point masks are converted into per-image reference
counts and are never presented as detection boxes.

Generated images and converted copies of external labels remain under the local,
ignored evaluation-data area. We commit conversion and validation code,
manifests, checksums, statistics, and documentation, but we do not mirror source
media or external annotations in Git.

## Project Categories

Category identifiers remain stable across every dataset version.

| ID | Category | Included objects |
| ---: | --- | --- |
| 1 | `person` | Visible individual people |
| 2 | `bicycle` | Pedal bicycles, including a bicycle being ridden |
| 3 | `motorcycle` | Motorcycles and motor scooters |
| 4 | `car_or_van` | Passenger cars, vans, and light commercial vans |
| 5 | `bus` | Road passenger buses and coaches |
| 6 | `truck` | Road freight trucks and lorries |

`road_vehicle_total` is calculated from categories 2 through 6. It is not an
annotation category. We do not create a `crowd` category because crowd
concentration is derived from individual `person` detections or from DLR-ACD
point counts.

Trains, boats, traffic lights, traffic signs, and other non-target objects are
not annotated. Tricycles and unusual vehicle types are excluded unless we can
map them consistently before the first benchmark run. Any taxonomy extension
requires an update to both this guide and the evaluation protocol.

## Bounding-Box Rules

### Visible extent

We draw a tight axis-aligned box around the visible object. The box includes the
object itself and avoids unnecessary road, pavement, shadow, or neighbouring
objects. Shadows are never treated as part of an object.

For a person riding a bicycle or motorcycle, the vehicle receives its vehicle
box and a separately visible rider may receive a `person` box when the source
annotation policy supports both labels. We record collection-specific mapping
differences rather than inventing missing labels.

### Occlusion

We annotate a partially hidden object when its category can still be identified
with reasonable confidence. The box covers the visible extent instead of an
estimated hidden shape. When two touching objects remain distinguishable, each
receives its own box. An inseparable cluster does not receive one large box.

### Image boundaries

A box that crosses an image boundary is clipped to valid image coordinates. We
retain the object when its category is identifiable and its visible centre lies
inside the image. Objects that appear only as an unidentifiable fragment at the
edge are excluded.

### Very small objects

Small aerial objects are retained when their class can be identified at normal
inspection zoom and a valid box can be drawn. A new manual box must be at least
4 pixels wide and 4 pixels high in the evaluation image. Smaller source labels
are preserved during conversion but flagged for review instead of silently
removed.

COCO size groups are reported from box area after conversion:

- small: area below `32 x 32` pixels;
- medium: area from `32 x 32` pixels up to, but not including, `96 x 96`
  pixels;
- large: area of at least `96 x 96` pixels.

### Ambiguous objects

We do not guess a category. If an object cannot be distinguished between two
project classes, it is excluded and recorded during quality control when the
ambiguity could materially affect the evaluation. A clearly visible van maps to
`car_or_van`; a large vehicle is not labelled as a bus or truck from size alone.

### Stationary objects

Visible vehicles are annotated regardless of whether they appear to be moving
or parked. A single aerial image cannot establish motion reliably. Restricting
counts to active road traffic belongs to later region or tracking logic, not to
the detector ground truth.

## Source Mapping Rules

We preserve the original source label alongside every converted category so
that mappings remain auditable.

| Collection label | Project category | Notes |
| --- | --- | --- |
| Traffic UAV `car` | `car_or_van` | The source does not separate cars and vans |
| Traffic UAV `motorbike` or `moto` | `motorcycle` | Source spelling is retained in provenance |
| Okutama `Person` | `person` | Coordinates are scaled from the source 4K space to the downloaded 720p frames |
| DLR person point | Count-only `person` reference | No bounding box is created |

Wikimedia examples require manual annotation only when they are selected for a
quantitative partition. Otherwise, they remain clearly identified qualitative
demonstration examples and are not included in metric calculations.

## Quality-Control Process

Every selected example passes two reviews before the dataset version is frozen.

1. The preparation pass converts or creates labels and records every warning.
2. The quality-control pass is performed separately from preparation. It
   overlays every box and checks missing objects, duplicates, category mappings,
   clipping, and image dimensions. It records the reviewer, date, decision, and
   number of corrections. If only one researcher is available, we state that
   the second pass was not independent.
3. Automated validation runs after corrections and must finish without errors.

The quality-control record distinguishes confirmed examples, corrected
examples, excluded examples, and unresolved examples. Unresolved examples are
not placed in validation or held-out test data.

## Split Rules

We split by `source_group_id`, never by individual frame. All frames from the
same video, flight, burst, or visually related sequence remain in one role.
Exact-file hashes and image-similarity checks are run before freezing the split.

The custom dataset targets training, validation, and held-out test roles. The
validation role may be used for model and threshold decisions. The held-out test
role is evaluated only after the complete configuration is frozen. Official
dataset splits, such as Okutama train and test, retain their published roles and
are reported separately from the custom split.

The split record includes the fixed seed `2026`, dataset version, manifest hash,
source groups, class frequencies, and COCO object-size distribution. If grouped
splitting cannot provide credible class coverage, we change the claimed scope or
add an independent licensed source instead of moving related frames between
roles.

## Validation Requirements

The automated validator must reject:

- missing or unreadable image files;
- duplicate asset identifiers or file hashes;
- unknown category identifiers;
- boxes with non-finite values, non-positive area, or coordinates outside the
  image after clipping;
- annotations whose recorded image dimensions differ from the actual file;
- missing source groups, licences, checksums, or dataset roles;
- source-group or file overlap between partitions; and
- held-out examples without a completed quality-control decision.

Warnings are reported separately for extremely small boxes, unusually large
boxes, low-support classes, severe class imbalance, and source-specific mapping
limitations. The final validation report becomes part of the thesis evidence.
