import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from app.config import (
    API_IMAGE_OUTPUT_DIR,
    API_IMAGE_UPLOAD_DIR,
    API_VIDEO_OUTPUT_DIR,
    API_VIDEO_UPLOAD_DIR,
)
from app.model_profile import DEVICE_PATTERN
from app.services.workload import WorkloadLimits

BYTES_PER_MEGABYTE = 1024 * 1024


class ApiSettingsError(ValueError):
    """Raised when API environment settings are invalid."""


@dataclass(frozen=True)
class ApiSettings:
    title: str = "Traffic and Crowd Monitoring API"
    version: str = "0.1.0"
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    image_upload_directory: Path = API_IMAGE_UPLOAD_DIR
    image_output_directory: Path = API_IMAGE_OUTPUT_DIR
    video_upload_directory: Path = API_VIDEO_UPLOAD_DIR
    video_output_directory: Path = API_VIDEO_OUTPUT_DIR
    max_image_upload_bytes: int = 10 * BYTES_PER_MEGABYTE
    max_image_pixels: int = 40_000_000
    max_grid_dimension: int = 20
    max_video_upload_bytes: int = 500 * BYTES_PER_MEGABYTE
    video_workers: int = 1
    model_device: str | None = None
    workload: WorkloadLimits = field(default_factory=WorkloadLimits)

    @classmethod
    def from_environment(cls) -> "ApiSettings":
        load_dotenv()
        raw_origins = os.getenv("API_CORS_ORIGINS", "http://localhost:5173")
        origins = tuple(
            origin.strip() for origin in raw_origins.split(",") if origin.strip()
        )
        for origin in origins:
            parsed = urlparse(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
            ):
                raise ApiSettingsError(
                    "API_CORS_ORIGINS must contain explicit HTTP or HTTPS origins"
                )
        max_upload_mb = _positive_environment_integer(
            "API_MAX_IMAGE_UPLOAD_MB", default=10
        )
        max_image_pixels = _positive_environment_integer(
            "API_MAX_IMAGE_PIXELS", default=40_000_000
        )
        max_grid_dimension = _positive_environment_integer(
            "API_MAX_GRID_DIMENSION", default=20
        )
        max_video_upload_mb = _positive_environment_integer(
            "API_MAX_VIDEO_UPLOAD_MB", default=500
        )
        video_workers = _positive_environment_integer("API_VIDEO_WORKERS", default=1)
        defaults = WorkloadLimits()
        try:
            workload = WorkloadLimits(
                **{
                    item.name: (
                        float if item.name == "min_sampling_interval_seconds" else int
                    )(
                        os.getenv(
                            f"API_{item.name.upper()}",
                            str(getattr(defaults, item.name)),
                        )
                    )
                    for item in fields(defaults)
                }
            )
        except ValueError as error:
            raise ApiSettingsError("Invalid API workload limits.") from error
        if video_workers > min(4, workload.max_inflight_analyses):
            raise ApiSettingsError(
                "API_VIDEO_WORKERS cannot exceed 4 or analysis capacity."
            )
        model_device = os.getenv("API_DEVICE")
        if model_device is not None and not DEVICE_PATTERN.fullmatch(model_device):
            raise ApiSettingsError("API_DEVICE must be cpu, cuda, or cuda:<index>")
        return cls(
            cors_origins=origins,
            max_image_upload_bytes=max_upload_mb * BYTES_PER_MEGABYTE,
            max_image_pixels=max_image_pixels,
            max_grid_dimension=max_grid_dimension,
            max_video_upload_bytes=max_video_upload_mb * BYTES_PER_MEGABYTE,
            video_workers=video_workers,
            model_device=model_device,
            workload=workload,
        )


def _positive_environment_integer(name: str, *, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ApiSettingsError(f"{name} must be a positive integer") from error
    if value < 1:
        raise ApiSettingsError(f"{name} must be a positive integer")
    return value
