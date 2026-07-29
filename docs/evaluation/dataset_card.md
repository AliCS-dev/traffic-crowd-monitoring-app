# Aerial Evaluation Dataset Card

## Current Status

- **Version:** 0.2
- **Last reviewed:** 29 July 2026
- **Status:** Initial source collection acquired and verified

This card records the data we selected for evaluating the aerial detection
pipeline. It is deliberately separate from the model results: the purpose here
is to establish where the data comes from, what it can measure, and where it is
weak before we inspect model performance.

The collection follows the class definitions, source grouping, and leakage
controls in the
[`evaluation protocol`](evaluation_protocol.md). The local
[`dataset manifest`](../../data/evaluation/manifest.csv) will record every
original image or video used by the project.

## Intended Use

We are building a small evaluation collection for four related purposes:

- measuring aerial vehicle detection on road scenes;
- measuring aerial person detection in video;
- measuring count error in dense crowds;
- checking how the application behaves on a few independent, naturally
  recorded examples.

These purposes require different annotations. Vehicle and person bounding boxes
support detection metrics such as precision, recall, and average precision.
Crowd point annotations support count-error metrics but do not support
bounding-box average precision. We will report those results separately.

The collection is not intended to establish the safety of an autonomous traffic
system, identify individuals, or make claims about all cities and crowd
conditions.

## Selected Collections

### Traffic Images Captured from UAVs

- **Collection identifier:** `traffic_uav`
- **Publisher:** Zenodo
- **Licence:** Creative Commons Attribution 4.0 International
- **Official record:** [Zenodo record 5776219](https://zenodo.org/records/5776219)
- **Dataset paper:** [Data, volume 7, issue 5, article 53](https://doi.org/10.3390/data7050053)

The publisher describes this collection as UAV-captured and includes regional
roads, urban intersections, rural roads, and roundabouts. Its annotations cover
cars and motorcycles in YOLO format. We selected it as the main labelled source
for vehicle detection and vehicle-count evaluation.

The collection does not cover our full vehicle taxonomy. In particular, it
cannot provide a balanced evaluation of buses, trucks, bicycles, or vans. Many
images are frames from related recordings, so their original scene or recording
must be retained as the source group. The downloaded PNG files do not contain
camera-platform metadata, so we cite the publisher's UAV description rather than
claiming that the platform can be independently identified from each archive.

### Okutama-Action

- **Collection identifier:** `okutama_action`
- **Publisher:** National Institute of Informatics and collaborating researchers
- **Licence:** Creative Commons Attribution-NonCommercial-ShareAlike 3.0
- **Official page:** [Okutama-Action](http://okutama-action.org/)

Okutama-Action provides aerial videos with person bounding boxes. It includes
changes in camera position, object scale, time of day, and drone configuration.
We selected it to measure person detection in moving aerial video.

The recordings contain staged human activities rather than naturally occurring
dense public crowds. We will therefore use them for person detection, not as
evidence that the system can estimate crowd density at large events.

### DLR Aerial Crowd Dataset

- **Collection identifier:** `dlr_acd`
- **Publisher:** German Aerospace Center (DLR)
- **Licence:** Creative Commons Attribution-NonCommercial-NoDerivatives 3.0
- **Official page:** [DLR Aerial Crowd Dataset](https://www.dlr.de/en/eoc/about-us/remote-sensing-technology-institute/photogrammetry-and-image-analysis/public-datasets/dlr-acd)

DLR-ACD contains 33 large aerial images captured with DSLR cameras mounted on a
helicopter during 16 flight campaigns over mass events and urban scenes. It
provides point annotations for individual people and is our dense-crowd count
reference. The ground sampling distance ranges from 4.5 to 15 centimetres per
pixel.

Point labels are not bounding boxes, so this collection contributes to count
MAE, normalized absolute error, and count bias rather than detection mAP. The
NoDerivatives term also means that we will retain the original media unchanged
and will not redistribute altered copies. Any thesis figure derived from this
collection will be reviewed against the licence before publication.

### Wikimedia Commons Samples

- **Collection identifier:** `wikimedia`
- **Publisher:** Individual creators through Wikimedia Commons
- **Licence:** Verified separately for every asset
- **Reuse guidance:** [Reusing content outside Wikimedia](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/en)

We selected four aerial traffic or crowd images and videos from Wikimedia
Commons. These examples provide independent application scenes that are not
drawn from the three research datasets.

Each selected file page identifies the creator, source, and licence. The exact
licence and attribution will also be carried into the evaluation manifest when
Issue #42 selects the final assets.

## Acquired Sources

The initial collection is deliberately smaller than the complete source
collections. It gives us labelled traffic sequences, the published Okutama train
and test sets, the complete DLR crowd collection, and four independent
application examples. Every downloaded file has a local SHA-256 checksum in
[`downloads.csv`](../../data/evaluation/downloads.csv).

### Traffic Archives

We selected three archives from the 34.7 GB Traffic UAV collection:

| Archive | Size | Publisher MD5 |
| --- | ---: | --- |
| `Roundabout(Near)_3.zip` | 403.3 MB | `3a2e70c0ad4e0400c87e04f139794382` |
| `Urban_intersection_2.zip` | 669.9 MB | `aff1885b3eb61b8bb2a66e4d1a08853c` |
| `Urban_intersection_4.zip` | 635.3 MB | `86b2ea63ae12f645a443c1378de336cd` |

This 1.71 GB subset contains 1,279 labelled frames. Inspection showed that the
two urban archives depict the same location from closely related low-oblique
viewpoints, so we treat them as one source group. The roundabout archive is a
separate scene and source group.

### Okutama Archives

We selected the published 1280 x 720 frame sets:

| Archive | Downloaded size | Published role |
| --- | ---: | --- |
| `TrainSetFrames.zip` | 5.77 GB | Training |
| `TestSetFrames.zip` | 1.65 GB | Test |

The 720p train and test archives preserve the dataset's published partition and
remain considerably smaller than the 18 GB 4K version. We do not move sequences
between the published train and test sets.

### DLR Archive

We acquired the complete `DLR_AerialCrowdDataset.zip` archive, reported as
349 MB on the official DLR page. The publisher does not display a checksum on
that page, so we recorded our downloaded file's SHA-256 value and retained the
archive unchanged.

### Wikimedia Assets

The following files add conditions that are missing or difficult to publish from
the research datasets:

| Asset | Size | Licence | Purpose |
| --- | ---: | --- | --- |
| [Jane M. Byrne Interchange Traffic.webm](https://commons.wikimedia.org/wiki/File:Jane_M._Byrne_Interchange_Traffic.webm) | 65.72 MB | CC BY-SA 4.0 | Daytime traffic video |
| [Ren'ai Dunhua traffic circle 202006.jpg](https://commons.wikimedia.org/wiki/File:Ren%27ai_Dunhua_traffic_circle_202006.jpg) | 2.67 MB | CC BY 2.0 | Daytime urban roundabout |
| [Renai Roundabout at night from the air.jpg](https://commons.wikimedia.org/wiki/File:Renai_Roundabout_at_night_from_the_air.jpg) | 2.71 MB | CC BY 2.0 | Same location at night |
| [Festival From Above.jpg](https://commons.wikimedia.org/wiki/File:Festival_From_Above.jpg) | 5.56 MB | CC BY-SA 4.0 | Modern dense-crowd example |

The two Renai images form one source group because they depict the same location
and were created by the same photographer. They provide a useful controlled
lighting comparison but will never be split across dataset partitions. The
festival image can support a publishable qualitative example; it does not replace
the point-count evaluation provided by DLR-ACD.

### Storage Estimate

| Collection | Approximate download |
| --- | ---: |
| Traffic UAV subset | 1.71 GB |
| Okutama 720p train and test | 7.42 GB |
| DLR-ACD | 0.37 GB |
| Wikimedia samples | 0.08 GB |
| **Total** | **9.58 GB** |

The downloaded files occupy 9.58 GB in decimal units, or approximately
8.92 GiB. Archives and extracted media currently occupy about 19 GiB under
`data/evaluation/raw/` and remain outside Git.

## Verification Results

### Traffic UAV

All three Traffic UAV archives matched the MD5 values published by Zenodo and
passed ZIP integrity tests. Together they contain 1,279 paired 1280 x 720 PNG
images and YOLO label files. Every label row has five fields, all image-label
pairs are present, and all normalized coordinates are within the expected
range.

| Archive | Frames | Cars | Motorcycles |
| --- | ---: | ---: | ---: |
| `Roundabout(Near)_3.zip` | 342 | 4,754 | 227 |
| `Urban_intersection_2.zip` | 461 | 2,250 | 0 |
| `Urban_intersection_4.zip` | 476 | 2,519 | 0 |
| **Total** | **1,279** | **9,523** | **227** |

The roundabout frames form one sunny sequence with substantial similarity
between adjacent frames. The two urban archives show the same sunny roadside
location from slightly different low-oblique positions. Their view resembles an
elevated roadside camera more than a nadir aerial image. Because the publisher
describes the collection as UAV-captured but the archives contain no
camera-platform metadata, we record the platform as publisher-reported rather
than independently verified.

The two urban archives belong to one source group. The roundabout archive forms
a second source group. Issue #42 will select separated frames within these
groups instead of treating adjacent frames as independent samples.

The source class-name files are not entirely consistent: the second class is
called `motorbike` in two archives and `moto` in
`Urban_intersection_2`. That archive contains no instances of class 1, so this
wording difference does not affect its current annotations.

### Okutama-Action

Both official 720p archives passed ZIP integrity tests. The published training
package contains 60,039 frames across 33 sequences, while the published test
package contains 17,326 frames across 10 sequences. We identified 17 source
groups in training and five in testing by grouping the two drone views that
share the same part-of-day and scenario numbers. No source group appears in both
published partitions.

The single-action tracking labels contain 333,720 person rows in training and
73,385 in testing. Their coordinates refer to the original 3840 x 2160 videos,
although the downloaded images are 1280 x 720. A visual overlay confirmed that
coordinates must therefore be divided by three when the labels are converted in
Issue #42.

Seven training boxes extend two to five pixels beyond the 3840-pixel right
boundary. We retain the original labels unchanged and will clip those boxes
during conversion. Another 2,802 rows contain a person box without an action
field. They remain valid for pedestrian detection because this project ignores
the action columns.

### DLR-ACD

The DLR archive passed its ZIP integrity test and contains 33 matching image and
binary point-mask pairs: 19 in the published training directory and 14 in the
published test directory. The masks use values 0 and 255, with one foreground
pixel representing a person annotation.

Counting the foreground pixels gives 226,336 points. The official page and
archive README report 226,291 annotations, a difference of 45. We record this
small discrepancy rather than changing the source. Issue #43 will calculate
reference counts directly from the supplied masks and report that method.

### Wikimedia Commons

All four Wikimedia files matched the SHA-1 values returned by the Commons API.
We also stored SHA-256 checksums locally.

- Sea Cow's 31.264-second Jane M. Byrne Interchange drone video is
  1920 x 1080 and licensed under CC BY-SA 4.0.
- MiNe's matched Renai day and night images are 2160 x 1620, licensed under
  CC BY 2.0, and contain DJI FC7203 metadata.
- Amdadphoto's 4000 x 3000 festival image is licensed under CC BY-SA 4.0 and
  adds a dense, near-nadir crowd scene.

The two Renai images remain one source group because they show the same location
and come from the same creator. The Commons examples have no reference
annotations yet; Issue #42 will decide which are suitable for manual annotation
and which should remain qualitative examples.

## Class Mapping

The source labels will later be converted to the operational taxonomy fixed in
Issue #40:

| Source label | Operational class | Use |
| --- | --- | --- |
| Traffic UAV `car` | `car_or_van` | Detection and count metrics |
| Traffic UAV class 1 (`motorbike` or `moto`) | `motorcycle` | Detection and count metrics |
| Okutama `Person` | `person` | Detection and count metrics |
| DLR person point | `person` count reference | Count metrics only |

Mappings for Wikimedia assets will be defined after those assets are selected
and annotated. We will not silently infer unsupported classes from a source.

## Selection Criteria

We will favour assets that add useful variation in:

- scene and recording source;
- camera angle and altitude;
- object size and density;
- road or public-space layout;
- lighting and weather;
- low, medium, and high activity;
- target classes; and
- empty or difficult scenes that can reveal false positives.

We will avoid collecting many nearly identical frames from one video. Every
video, flight, burst, or related scene receives a source-group identifier before
dataset partitions are created.

## Provenance And Storage

The project tracks metadata in
[`data/evaluation/manifest.csv`](../../data/evaluation/manifest.csv). Original
media is stored under `data/evaluation/raw/`, which is ignored by Git. The
manifest records the original filename, local path, source URL, creator or
publisher, licence, access date, SHA-256 checksum, source group, and intended
role.

We will not mirror the selected datasets in the GitHub repository. Anyone
reproducing the evaluation must obtain the original files from their publishers
and comply with the corresponding licences.

## Privacy And Ethics

The application counts object categories and does not perform face recognition,
identity tracking, or demographic classification. Nevertheless, aerial media can
contain people, vehicles, private property, and location information.

We will use established research datasets and openly licensed media, minimise
the amount of copied visual data, and avoid identifying individuals. Licence
terms do not replace privacy or research-ethics responsibilities, so questionable
assets will be excluded even when they appear technically reusable.

## Known Gaps And Biases

The initial collection has several known limitations:

- the labelled traffic subset is dominated by cars, with motorcycles present
  only in the roundabout sequence;
- the two urban traffic archives cover one low-oblique location and do not add
  independent scene diversity;
- Okutama contains staged actions and relatively small groups;
- DLR-ACD contains dense crowds but no person bounding boxes;
- the source countries and public-space layouts are not representative of every
  city;
- rare classes such as buses, trucks, and bicycles may remain underrepresented;
- only one independent traffic image represents nighttime conditions, and
  poor-weather conditions are absent;
- different annotation types prevent one combined score across all sources.

We will report these gaps with the evaluation results. If a core class or
condition cannot be tested fairly, we will narrow the thesis claim or collect
additional licensed material rather than treating missing evidence as a
successful result.

## Next Work

Issue #41 establishes source selection, provenance, licensing, local storage,
and the limitations discovered during inspection. Issue #42 will define the
reviewed subset, convert annotation formats, apply class mappings, preserve
source-grouped partitions, and check for duplicates. Model benchmarking and
tuning will begin only after those dataset decisions are fixed.
