import cv2
import numpy as np
import pytest

from app.services.video_service import VideoReader


class FakeVideoCapture:
    def __init__(self, opened=True, frames=None):
        self.opened = opened
        self.frames = list(frames or [])
        self.released = False
        self.properties = {
            cv2.CAP_PROP_FRAME_WIDTH: 1920,
            cv2.CAP_PROP_FRAME_HEIGHT: 1080,
            cv2.CAP_PROP_FPS: 30,
            cv2.CAP_PROP_FRAME_COUNT: 150,
        }

    def isOpened(self):
        return self.opened

    def get(self, property_id):
        return self.properties.get(property_id, 0)

    def read(self):
        if not self.frames:
            return False, None

        return True, self.frames.pop(0)

    def release(self):
        self.released = True


def test_missing_video_file_raises_error():
    with pytest.raises(FileNotFoundError):
        VideoReader("data/input/missing_video.mp4")


def test_unsupported_video_format_raises_error(tmp_path):
    video_path = tmp_path / "video.txt"
    video_path.write_text("not a video")

    with pytest.raises(ValueError, match="Unsupported video format"):
        VideoReader(video_path)


def test_unreadable_video_releases_capture(tmp_path, monkeypatch):
    video_path = tmp_path / "unreadable.mp4"
    video_path.write_bytes(b"not a valid video")
    fake_capture = FakeVideoCapture(opened=False)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: fake_capture)

    with pytest.raises(ValueError, match="Video could not be opened"):
        VideoReader(video_path)

    assert fake_capture.released is True


def test_video_metadata_is_extracted(tmp_path, monkeypatch):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"video data")
    fake_capture = FakeVideoCapture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: fake_capture)

    with VideoReader(video_path) as video_reader:
        metadata = video_reader.metadata

        assert metadata.path == video_path
        assert metadata.width == 1920
        assert metadata.height == 1080
        assert metadata.fps == 30
        assert metadata.frame_count == 150
        assert metadata.duration_seconds == 5

    assert fake_capture.released is True


def test_video_frames_are_read_in_order(tmp_path, monkeypatch):
    video_path = tmp_path / "sample.avi"
    video_path.write_bytes(b"video data")
    first_frame = np.zeros((2, 2, 3), dtype=np.uint8)
    second_frame = np.ones((2, 2, 3), dtype=np.uint8)
    fake_capture = FakeVideoCapture(frames=[first_frame, second_frame])
    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: fake_capture)

    with VideoReader(video_path) as video_reader:
        assert np.array_equal(video_reader.read_next_frame(), first_frame)
        assert np.array_equal(video_reader.read_next_frame(), second_frame)
        assert video_reader.read_next_frame() is None

    with pytest.raises(RuntimeError, match="Video reader is closed"):
        video_reader.read_next_frame()
