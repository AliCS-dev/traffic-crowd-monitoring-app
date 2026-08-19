from pathlib import Path

import numpy as np
import pytest

from app.services.frame_sampling_service import (
    calculate_sampled_frame_count,
    sample_video_frames,
)
from app.services.video_service import VideoMetadata


class FakeVideoReader:
    def __init__(self, frames, fps):
        self.metadata = VideoMetadata(
            path=Path("sample.mp4"),
            width=2,
            height=2,
            fps=fps,
            frame_count=len(frames),
            duration_seconds=len(frames) / fps if fps > 0 else None,
        )
        self._frames = iter(frames)

    def read_next_frame(self):
        return next(self._frames, None)


def create_frames(count):
    return [
        np.full((2, 2, 3), fill_value=frame_number, dtype=np.uint8)
        for frame_number in range(count)
    ]


def test_frames_are_sampled_at_time_interval():
    frames = create_frames(5)
    video_reader = FakeVideoReader(frames, fps=2)

    sampled_frames = list(
        sample_video_frames(video_reader, sampling_interval_seconds=1)
    )

    assert [frame.frame_number for frame in sampled_frames] == [0, 2, 4]
    assert [frame.timestamp_seconds for frame in sampled_frames] == [0, 1, 2]
    assert sampled_frames[0].image is frames[0]
    assert sampled_frames[1].image is frames[2]
    assert sampled_frames[2].image is frames[4]


def test_fractional_sampling_interval():
    video_reader = FakeVideoReader(create_frames(6), fps=4)

    sampled_frames = list(
        sample_video_frames(video_reader, sampling_interval_seconds=0.5)
    )

    assert [frame.frame_number for frame in sampled_frames] == [0, 2, 4]
    assert [frame.timestamp_seconds for frame in sampled_frames] == [0, 0.5, 1]


def test_interval_shorter_than_frame_duration_samples_every_frame():
    video_reader = FakeVideoReader(create_frames(3), fps=2)

    sampled_frames = list(
        sample_video_frames(video_reader, sampling_interval_seconds=0.1)
    )

    assert [frame.frame_number for frame in sampled_frames] == [0, 1, 2]


@pytest.mark.parametrize("sampling_interval", [0, -1, float("inf"), float("nan")])
def test_invalid_sampling_interval_raises_error(sampling_interval):
    video_reader = FakeVideoReader(create_frames(1), fps=30)

    with pytest.raises(ValueError, match="Sampling interval"):
        list(sample_video_frames(video_reader, sampling_interval))


@pytest.mark.parametrize("fps", [0, float("inf"), float("nan")])
def test_invalid_video_fps_raises_error(fps):
    video_reader = FakeVideoReader(create_frames(1), fps=fps)

    with pytest.raises(ValueError, match="Video FPS"):
        list(sample_video_frames(video_reader, sampling_interval_seconds=1))


def test_empty_video_produces_no_sampled_frames():
    video_reader = FakeVideoReader([], fps=30)

    sampled_frames = list(
        sample_video_frames(video_reader, sampling_interval_seconds=1)
    )

    assert sampled_frames == []


def test_sampled_frame_count_matches_sampling_sequence():
    assert calculate_sampled_frame_count(5, fps=2, sampling_interval_seconds=1) == 3
    assert calculate_sampled_frame_count(6, fps=4, sampling_interval_seconds=0.5) == 3
