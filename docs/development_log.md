# Development Log

## Issue #7 — Integrate object detection model for image input

Date: 17 May 2026

### Objective
The objective of this issue was to integrate an object detection model into the application pipeline for single image input.

### Work completed
- Added an initial detector script using Ultralytics YOLO.
- Loaded a sample aerial image from the input folder.
- Ran object detection on the image.
- Printed detected object classes and confidence scores.
- Tested different inference image sizes.
- Observed that increasing the inference image size improved detection of small vehicles in aerial imagery.

### Technical observation
The sample image contains small vehicles due to the aerial top-down perspective. Initial detection performance was limited when using a smaller inference image size. Increasing the inference image size improved the detection output, which is relevant to the aerial monitoring use case.

### Current limitation
The current implementation is a demo version. The image path is manually defined in the detector script, and the detector has not yet been refactored into the final application structure.

### Next step
The next development issue should improve image input handling so that image paths can be provided dynamically.