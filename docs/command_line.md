# Command-Line Processing

[Documentation index](README.md) | [Local setup](local_development.md)

These examples use the local Python environment and model described in the
setup guide. Paths such as `data/input/example.jpg` are placeholders for your
own media. The CLI processes images; video uploads are available in the browser
and [API](api.md).

## Trying the Image Pipeline

The default command processes the sample image included in the repository:

```bash
.venv/bin/python -m app.main
```

We can also choose a different image and output location:

```bash
.venv/bin/python -m app.main \
  --image data/input/example.jpg \
  --output data/output/example_detected.jpg
```

The complete list of command-line options is available with:

```bash
.venv/bin/python -m app.main --help
```

## Counting Objects In Grid Cells

We can divide the processed image into a grid and count detections according to
the centre of each bounding box. For example, this command uses three rows and
four columns:

```bash
.venv/bin/python -m app.main \
  --image data/input/example.jpg \
  --grid 3 4
```

The terminal summary reports only occupied cells. The grid service itself
returns every cell, including empty cells, in stable row-major order so that a
browser can render a complete grid without rebuilding it.

We can store the same grid together with the image result by combining the grid
and database options:

```bash
.venv/bin/python -m app.main \
  --image data/input/example.jpg \
  --grid 3 4 \
  --save-to-db \
  --session-name "three-by-four grid example"
```

Every cell is stored so its layout can be reconstructed later. Per-cell summary
rows are created only for classes actually counted in a cell; empty cells do not
receive artificial zero-count rows. Complete-frame summaries remain separate
and have no grid-cell reference.

Grid counts are relative image-region counts. They depend on the detector's
predictions and do not represent people or vehicles per square metre. The
current command does not draw the grid on the output image.

## Experimental Threshold Notifications

Image and video analyses evaluate the tracked rules in
`configs/runtime/alert_rules.json`. A rule names one object class, selects either
the complete frame or each grid cell, declares whether equality triggers it, and
assigns an information, warning, or critical display level. The current file has
two illustrative rules:

- at least 20 `car_or_van` detections in one frame produces a warning;
- at least 8 `person` detections in one grid cell produces an information notice.

These values are application configuration, not research findings or public
safety limits. A generated alert means only that a model-produced count met its
configured software threshold. It does not establish traffic congestion,
physical crowd density, danger, or an emergency. The complete rule format,
boundary behavior, and limitations are described in the
[alert-rule documentation](alert_rules.md).

## Reading And Sampling Video Input

The video service validates common video formats, reads basic metadata, and gives
us sequential access to frames. The sampling service selects frames at a
user-defined interval while preserving each selected frame's number and
timestamp. The video detection service reuses one model instance across those
frames:

```python
from app.database.detection_repository import save_video_detection_results
from app.model_profile import load_runtime_model_profile
from app.services.detection_service import ObjectDetector
from app.services.frame_sampling_service import sample_video_frames
from app.services.video_detection_service import process_sampled_video_frames
from app.services.video_service import VideoReader

profile = load_runtime_model_profile()
detector = ObjectDetector.from_runtime_profile(profile)

with VideoReader("data/input/example.mp4") as video:
    sampled_frames = sample_video_frames(
        video,
        sampling_interval_seconds=1.0,
    )
    frame_results = list(
        process_sampled_video_frames(sampled_frames, detector, profile)
    )

stored_result = save_video_detection_results(
    "data/input/example.mp4",
    frame_results,
    session_name="sample video run",
    model_profile=profile,
)
print(stored_result)
```

Supported formats are MP4, AVI, MOV, and MKV. The context manager closes the
OpenCV video resource when we finish reading. Video persistence stores one
session and input source for the video, followed by one processed-frame row for
each sampled frame. API video jobs also save one annotated JPEG for every sampled
frame. The command-line application still handles image runs only. The video API
composes these services in a bounded background worker.
