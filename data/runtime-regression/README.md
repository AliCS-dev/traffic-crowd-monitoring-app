# Runtime Regression Fixtures

We use two original PNGs and a short derived MJPEG video from the validation
sequence `traffic_roundabout_near_3`. These are development fixtures, not a new
held-out test set. No reference annotations or accuracy scores are involved.

Source: [Traffic images captured from UAVs](https://zenodo.org/records/5776219),
version 1, by Sergio Ghisler, Javier Sanchez-Soriano and Sergio Bemposta Rosende.
The publisher's record and API identify the licence as
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), checked 22 September 2026.
Attribution applies to all media in `fixtures/`; no endorsement is implied.
Dataset paper: Bemposta Rosende et al., *Data* 2022, 7, 53,
[doi:10.3390/data7050053](https://doi.org/10.3390/data7050053).

The PNGs are unchanged. The video repeats each of source frames 6, 18 and 29 ten
times at 10 fps and encodes them as MJPEG. Its three-second timeline is artificial:
it checks decoding and sampling, not traffic motion or real elapsed time. The
manifest records source IDs, roles, checksums, transformations and tolerances.
We distribute these derivatives under CC BY 4.0 with this attribution.

`scripts/prepare_runtime_fixtures.py` rebuilds the fixture from the already
downloaded archive after verifying the source hashes and validation role.
Video encoding can differ by OpenCV/codec version: the committed bytes and
manifest hashes are the comparison input, not an arbitrary regenerated video.
Changing the fixture requires an explicit new baseline and review.

Counts must match by class. A one-to-one match permits at most 0.5 pixels per
box coordinate and 0.0001 confidence difference. Output JPEG hashes must match
exactly; rendering-only changes still require review. These thresholds were
declared before establishing the initial reference. A pass on this tiny
one-scene set does not establish model equivalence or accuracy.
