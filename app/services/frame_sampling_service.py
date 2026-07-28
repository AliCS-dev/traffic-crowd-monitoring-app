import math
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from app.services.video_service import VideoReader


@dataclass(frozen=True)
class SampledFrame:
    frame_number: int
    timestamp_seconds: float
    image: np.ndarray


def sample_video_frames(
    video_reader: VideoReader,
    sampling_interval_seconds: float,
) -> Iterator[SampledFrame]:
    if not math.isfinite(sampling_interval_seconds) or sampling_interval_seconds <= 0:
        raise ValueError("Sampling interval must be a positive finite number.")

    fps = video_reader.metadata.fps
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("Video FPS must be positive for time-based sampling.")

    frame_interval = max(1, round(sampling_interval_seconds * fps))
    frame_number = 0

    while True:
        frame = video_reader.read_next_frame()
        if frame is None:
            return

        if frame_number % frame_interval == 0:
            yield SampledFrame(
                frame_number=frame_number,
                timestamp_seconds=frame_number / fps,
                image=frame,
            )

        frame_number += 1
