from dataclasses import dataclass
from pathlib import Path

import cv2

SUPPORTED_VIDEO_FORMATS = {".avi", ".mkv", ".mov", ".mp4"}


@dataclass(frozen=True)
class VideoMetadata:
    path: Path
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float | None


class VideoReader:
    def __init__(self, video_path):
        self.path = Path(video_path)
        self._validate_path()

        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"Video could not be opened: {self.path}")

        self._capture = capture
        self.metadata = self._read_metadata()

    def _validate_path(self):
        if not self.path.is_file():
            raise FileNotFoundError(f"Video not found: {self.path}")

        if self.path.suffix.lower() not in SUPPORTED_VIDEO_FORMATS:
            supported_formats = ", ".join(
                suffix.removeprefix(".").upper()
                for suffix in sorted(SUPPORTED_VIDEO_FORMATS)
            )
            raise ValueError(
                f"Unsupported video format. Please use {supported_formats}."
            )

    def _read_metadata(self):
        width = max(0, int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = max(0, int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        fps = max(0.0, float(self._capture.get(cv2.CAP_PROP_FPS)))
        frame_count = max(0, int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        duration_seconds = frame_count / fps if fps > 0 else None

        return VideoMetadata(
            path=self.path,
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            duration_seconds=duration_seconds,
        )

    def read_next_frame(self):
        if self._capture is None:
            raise RuntimeError("Video reader is closed.")

        frame_available, frame = self._capture.read()
        if not frame_available:
            return None

        return frame

    def close(self):
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self):
        return self

    def __exit__(self, _exception_type, _exception, _traceback):
        self.close()
