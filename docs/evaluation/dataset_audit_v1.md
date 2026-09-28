# Historical Dataset Coverage Audit

We audited the existing evaluation data on 28 September 2026 as the first part
of issue #113. The purpose is to identify what we can reuse and what is missing
before we define evaluation v2. We did not run inference, train a model, change
annotations or move images between splits. The failed historical quality gate
and unsupported dense-crowd decision remain unchanged.

The reproducible counts are in
[`dataset_audit_v1.json`](../../data/evaluation/dataset_audit_v1.json). Here, v1
means the historical dataset; its manifest still uses the version `1.0-draft`.
This report is not a new accuracy result or an independent final holdout.

## Coverage

We have 346 images: 313 with bounding-box annotations and 33 with point-count
references. There are 28 recorded source groups, but these are not necessarily
28 independent locations or flights. In particular, the DLR groups describe
dataset partitions rather than independently verified capture sessions.

| Collection | Images | Recorded groups | Main evidence |
| --- | ---: | ---: | --- |
| Traffic Images Captured from UAVs | 90 | 2 | Car/van and motorcycle boxes |
| Okutama-Action | 215 | 22 | Person boxes in staged activity scenes |
| Wikimedia | 8 | 2 | Vehicle boxes from two video sources |
| DLR-ACD | 33 | 2 | 226,336 reference people, represented as point counts |

Point counts are not person bounding boxes. We keep the two annotation types
separate rather than presenting the large DLR total as detection-label coverage.
The table below includes only boxes within each image's declared target classes,
matching our existing evaluation loader. Another 79 Wikimedia person boxes exist
in the canonical files but are outside those images' declared evaluation scope.
They remain in the original files and are reported separately in the JSON.

| Class | In-scope boxes | Images with boxes | Groups with boxes | Small | Medium | Large |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Person | 1,176 | 192 | 22 | 711 | 465 | 0 |
| Bicycle | 0 | 0 | 0 | 0 | 0 | 0 |
| Motorcycle | 38 | 16 | 2 | 19 | 19 | 0 |
| Car or van | 2,115 | 98 | 4 | 1,451 | 597 | 67 |
| Bus | 10 | 5 | 2 | 3 | 3 | 4 |
| Truck | 38 | 8 | 2 | 18 | 17 | 3 |

We classify area in native image pixels: small is below 32 squared, medium is
at least 32 squared but below 96 squared, and large is at least 96 squared.
These are descriptive size bands, not model input sizes or measured size-specific
accuracy. Of 3,377 in-scope boxes, 2,202 are small. None has a side below four
pixels. Images and groups can appear in more than one class row.

## Split Limitations

| Historical role | Images | Person | Car/van | Motorcycle | Bus | Truck | Bicycle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Training | 130 | 749 | 0 | 0 | 0 | 0 | 0 |
| Validation | 86 | 180 | 528 | 38 | 6 | 3 | 0 |
| Held-out test | 130 | 247 | 1,587 | 0 | 4 | 35 | 0 |

The class columns count boxes, not images. The training split shown here belongs
to our local evaluation manifest, not the pretrained models' original datasets.
It provides no vehicle examples for a balanced local traffic fine-tuning run.
Zero bicycle support means we cannot estimate bicycle accuracy from this data;
motorcycles also have no historical test support. Four held-out bus boxes give
very little evidence for a general bus-detection claim.

No recorded source group crosses roles, and no exact image hashes are duplicated.
However, all 215 Okutama images share the broad location label `Okutama Japan`,
across training, validation and test. Another 123 images have no recorded
location. This audit does not assess near-duplicates or verify independence of
locations, flights and capture sessions. Passing the hash/group checks is not
proof that the dataset measures generalization to unseen locations.

The historical test has already been evaluated. We can retain it for historical
comparison, but cannot rename it as an untouched v2 final holdout.

## Scene And Annotation Limits

The metadata records 90 low-oblique images, eight aerial-oblique images and 215
with the less specific label `aerial`. The only 33 explicitly nadir-labelled
images are DLR point-count scenes. We therefore have no explicitly nadir-labelled
traffic bounding-box subset in this manifest; we have not inferred camera angles
from the generic labels.

There is only one night-labelled image. Weather is recorded as clear for 98
images and not recorded for 248, so we cannot claim adverse-weather coverage.
Occlusion is marked for 62 Okutama boxes and absent for another 1,114; all 2,201
in-scope traffic/Wikimedia boxes have unknown occlusion. Unknown does not mean
unoccluded. All in-scope person boxes come from the staged Okutama collection,
which limits their relevance to ordinary pedestrian scenes.

The review ledger records 341 confirmed and five corrected images under Ali's
name, with dates. The manifest nevertheless still marks all 346 as `pending`.
We report this discrepancy without rewriting historical provenance. Reading a
review record does not independently establish who reviewed it or whether every
box is correct; this audit is not a new human annotation review. A v2 release
needs a consistent, explicitly confirmed review record. The four previously
excluded Jane Byrne frames remain excluded.

Every manifest entry has source and licence links and a licence identifier.
This checks metadata completeness, not current permission or licence compliance.
All 346 local media checksums match the manifest. The existing technical dataset
validator also passes; technical readiness is separate from representative
coverage and model quality.

## What We Do Next

We can reuse the historical data, annotations and measured failures as documented
development evidence. We should not expand application claims on this basis.
Before acquiring more data, we need to agree the v2 traffic classes, camera
views and pedestrian scenarios we actually intend to support, with dense crowds
kept as a separate task. We can then declare coverage targets, independent-source
splits, uncertainty reporting and pass thresholds before inspecting new final
test predictions.

Issue #113 remains in progress. This audit does not complete its acquisition,
annotation review, v2 manifest or independent-holdout requirements. The original
[dataset card](dataset_card.md) remains a dated acquisition snapshot; the
[results index](results_index.md) connects this coverage report to the actual
accuracy results.

## Reproduction

From the repository root, with the existing local evaluation media available:

```bash
.venv/bin/python scripts/validate_evaluation_dataset.py
.venv/bin/python scripts/audit_evaluation_dataset.py --verify-media --output data/evaluation/dataset_audit_v1.json
.venv/bin/python -m pytest tests/test_dataset_audit.py -q
```

The report includes SHA-256 hashes of the manifest, reviews, exclusions and
canonical annotation inputs. Omitting `--verify-media` allows a metadata-only
audit and records that image hashes were not verified. The audit does not load a
model, contact a database or alter the dataset. Its CLI refuses to overwrite a
manifest, review ledger, exclusions file, canonical annotation or selected image.
