import math
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from app.services.video_service import VideoMetadata, VideoReader

READ_CHUNK_SIZE = 1024 * 1024
HEADER_SIZE = 16
MIME_BY_SUFFIX = {
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
}


class VideoUploadError(ValueError):
    """Base class for video upload validation failures."""


class UnsupportedVideoUploadError(VideoUploadError):
    """Raised when declared or detected video formats are unsupported."""


class VideoUploadTooLargeError(VideoUploadError):
    """Raised when uploaded bytes or frame dimensions exceed configured limits."""


class InvalidVideoUploadError(VideoUploadError):
    """Raised when an uploaded file cannot be decoded as a valid video."""


@dataclass(frozen=True)
class VideoUploadPolicy:
    max_bytes: int
    max_frame_pixels: int

    def __post_init__(self) -> None:
        if self.max_bytes < 1 or self.max_frame_pixels < 1:
            raise ValueError("Video upload limits must be positive integers.")


@dataclass(frozen=True)
class StoredVideoUpload:
    asset_id: UUID
    original_filename: str
    path: Path
    metadata: VideoMetadata


def store_validated_video_upload(
    file: BinaryIO,
    *,
    filename: str | None,
    content_type: str | None,
    upload_directory: Path,
    policy: VideoUploadPolicy,
    asset_id_factory=uuid4,
    video_reader_factory=VideoReader,
) -> StoredVideoUpload:
    original_filename = _safe_original_filename(filename)
    suffix = Path(original_filename).suffix.lower()
    expected_mime = MIME_BY_SUFFIX.get(suffix)
    if expected_mime is None:
        raise UnsupportedVideoUploadError(
            "Only MP4, AVI, MOV, and MKV video uploads are supported."
        )
    if content_type != expected_mime:
        raise UnsupportedVideoUploadError(
            "The uploaded video MIME type does not match its extension."
        )

    upload_directory = Path(upload_directory)
    asset_id = asset_id_factory()
    final_path = upload_directory / f"{asset_id}{suffix}"
    temporary_path = upload_directory / f".{asset_id}.part"

    try:
        upload_directory.mkdir(parents=True, exist_ok=True)
        header, total_bytes = _write_bounded(file, temporary_path, policy.max_bytes)
        if total_bytes == 0:
            raise InvalidVideoUploadError("The uploaded video is empty.")
        if not _header_matches_suffix(header, suffix):
            raise UnsupportedVideoUploadError(
                "The uploaded video content does not match its extension."
            )

        temporary_path.replace(final_path)
        metadata = _inspect_video(final_path, video_reader_factory)
        if metadata.width * metadata.height > policy.max_frame_pixels:
            raise VideoUploadTooLargeError(
                "The video frame dimensions exceed the configured pixel limit."
            )

        return StoredVideoUpload(
            asset_id=asset_id,
            original_filename=original_filename,
            path=final_path,
            metadata=metadata,
        )
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


def _safe_original_filename(filename: str | None) -> str:
    if not filename:
        raise UnsupportedVideoUploadError("The video upload must have a filename.")
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not basename or len(basename) > 255 or any(ord(char) < 32 for char in basename):
        raise UnsupportedVideoUploadError("The video filename is invalid.")
    return basename


def _write_bounded(file: BinaryIO, path: Path, max_bytes: int) -> tuple[bytes, int]:
    header = bytearray()
    total_bytes = 0
    with path.open("xb") as handle:
        while True:
            chunk = file.read(min(READ_CHUNK_SIZE, max_bytes + 1 - total_bytes))
            if not chunk:
                break
            if len(header) < HEADER_SIZE:
                header.extend(chunk[: HEADER_SIZE - len(header)])
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise VideoUploadTooLargeError(
                    "The video upload exceeds the configured file-size limit."
                )
            handle.write(chunk)
    return bytes(header), total_bytes


def _header_matches_suffix(header: bytes, suffix: str) -> bool:
    if suffix in {".mp4", ".mov"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if suffix == ".avi":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI "
    if suffix == ".mkv":
        return header.startswith(b"\x1aE\xdf\xa3")
    return False


def _inspect_video(path: Path, video_reader_factory) -> VideoMetadata:
    try:
        with video_reader_factory(path) as reader:
            metadata = reader.metadata
            first_frame = reader.read_next_frame()
    except (OSError, RuntimeError, ValueError) as error:
        raise InvalidVideoUploadError(
            "The uploaded file is not a readable video."
        ) from error

    if (
        metadata.width < 1
        or metadata.height < 1
        or not math.isfinite(metadata.fps)
        or metadata.fps <= 0
        or metadata.frame_count < 1
        or first_frame is None
        or getattr(first_frame, "size", 0) == 0
    ):
        raise InvalidVideoUploadError("The uploaded video metadata is invalid.")
    return metadata
