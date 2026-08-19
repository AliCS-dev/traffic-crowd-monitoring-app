from io import BytesIO
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

from app.services.video_service import VideoMetadata
from app.services.video_upload_service import (
    UnsupportedVideoUploadError,
    VideoUploadPolicy,
    VideoUploadTooLargeError,
    store_validated_video_upload,
)

ASSET_ID = UUID("12345678-1234-5678-1234-567812345678")
MP4_BYTES = b"\x00\x00\x00\x18ftypisom" + b"video"


class FakeReader:
    def __init__(self, path):
        self.metadata = VideoMetadata(
            path=Path(path),
            width=4,
            height=3,
            fps=2,
            frame_count=5,
            duration_seconds=2.5,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read_next_frame(self):
        return np.zeros((3, 4, 3), dtype=np.uint8)


def test_valid_video_is_streamed_to_a_server_generated_filename(tmp_path):
    result = store_validated_video_upload(
        BytesIO(MP4_BYTES),
        filename="folder/traffic.mp4",
        content_type="video/mp4",
        upload_directory=tmp_path,
        policy=VideoUploadPolicy(max_bytes=100, max_frame_pixels=100),
        asset_id_factory=lambda: ASSET_ID,
        video_reader_factory=FakeReader,
    )

    assert result.original_filename == "traffic.mp4"
    assert result.path == tmp_path / f"{ASSET_ID}.mp4"
    assert result.path.read_bytes() == MP4_BYTES


def test_oversized_or_mismatched_uploads_leave_no_files(tmp_path):
    with pytest.raises(VideoUploadTooLargeError):
        store_validated_video_upload(
            BytesIO(MP4_BYTES),
            filename="traffic.mp4",
            content_type="video/mp4",
            upload_directory=tmp_path,
            policy=VideoUploadPolicy(max_bytes=12, max_frame_pixels=100),
            video_reader_factory=FakeReader,
        )
    with pytest.raises(UnsupportedVideoUploadError):
        store_validated_video_upload(
            BytesIO(MP4_BYTES),
            filename="traffic.mp4",
            content_type="video/quicktime",
            upload_directory=tmp_path,
            policy=VideoUploadPolicy(max_bytes=100, max_frame_pixels=100),
            video_reader_factory=FakeReader,
        )

    assert list(tmp_path.iterdir()) == []
