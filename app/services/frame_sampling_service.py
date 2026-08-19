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
    fps = video_reader.metadata.fps
    frame_interval = calculate_frame_interval(fps, sampling_interval_seconds)
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


def calculate_frame_interval(fps: float, sampling_interval_seconds: float) -> int:
    if not math.isfinite(sampling_interval_seconds) or sampling_interval_seconds <= 0:
        raise ValueError("Sampling interval must be a positive finite number.")
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("Video FPS must be positive for time-based sampling.")
    return max(1, round(sampling_interval_seconds * fps))


def calculate_sampled_frame_count(
    frame_count: int,
    fps: float,
    sampling_interval_seconds: float,
) -> int:
    if isinstance(frame_count, bool) or not isinstance(frame_count, int):
        raise ValueError("Video frame count must be a positive integer.")
    if frame_count < 1:
        raise ValueError("Video frame count must be a positive integer.")
    frame_interval = calculate_frame_interval(fps, sampling_interval_seconds)
    return ((frame_count - 1) // frame_interval) + 1
