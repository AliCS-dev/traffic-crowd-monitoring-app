import math
from dataclasses import dataclass, fields
from threading import BoundedSemaphore


class AnalysisBusyError(RuntimeError):
    """Raised before accepting more work than this process can hold."""


class AnalysisTimeoutError(RuntimeError):
    """Raised at a cooperative processing deadline."""


@dataclass(frozen=True)
class WorkloadLimits:
    max_inflight_analyses: int = 3
    max_video_duration_seconds: int = 300
    max_video_source_frames: int = 36_000
    max_sampled_frames: int = 300
    max_video_detection_records: int = 100_000
    max_processed_pixels: int = 40_000_000
    min_sampling_interval_seconds: float = 0.25
    max_queue_seconds: int = 60
    max_processing_seconds: int = 300

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field.name} must be positive and finite.")
            if field.name != "min_sampling_interval_seconds" and not isinstance(
                value, int
            ):
                raise ValueError(f"{field.name} must be an integer.")
        if self.min_sampling_interval_seconds > 1:
            raise ValueError(
                "Minimum sampling interval must not exceed the 1s default."
            )


class WorkloadAdmission:
    """Bound running and queued image/video work together in one API process."""

    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("Workload capacity must be positive.")
        self._slots = BoundedSemaphore(capacity)

    def acquire(self):
        if not self._slots.acquire(blocking=False):
            raise AnalysisBusyError("Analysis capacity is full. Please retry later.")

    def release(self):
        self._slots.release()
