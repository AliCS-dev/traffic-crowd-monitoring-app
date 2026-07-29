# Evaluation Data

This directory holds the metadata for the aerial data used in our model-quality
gate. The images and videos themselves stay on the local machine because they
are large and remain subject to their original licences.

The evaluation protocol is defined in
[`docs/evaluation/evaluation_protocol.md`](../../docs/evaluation/evaluation_protocol.md),
and the selected collections and their limitations are described in
[`docs/evaluation/dataset_card.md`](../../docs/evaluation/dataset_card.md).

## Directory Layout

```text
data/evaluation/
├── README.md
├── downloads.csv         # Downloaded source packages and checksums
├── manifest.csv
└── raw/                  # Local media; ignored by Git
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

The manifest remains empty until we choose the evaluation subset. Bounding-box
conversion, new annotations, and train, validation, and test partitions belong
to Issue #42. This distinction matters for Okutama because its downloaded 720p
frames use labels expressed in the original 4K coordinate space, and for the
Traffic UAV data because related video frames must remain in the same source
group.
