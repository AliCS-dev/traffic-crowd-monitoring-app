"""Request-correlated stage durations; these are not detector accuracy scores."""

import logging
from contextlib import contextmanager
from time import monotonic

from app.logging_config import request_id_context

LOGGER = logging.getLogger(__name__)


def record_stage(stage: str, seconds: float, *, status: str, **fields) -> None:
    LOGGER.info(
        "stage_timing",
        extra={
            "stage": stage,
            "duration_seconds": seconds,
            "stage_status": status,
            "request_id": request_id_context.get(),
            **fields,
        },
    )


@contextmanager
def measure_stage(stage: str):
    started = monotonic()
    status = "failed"
    try:
        yield
        status = "completed"
    finally:
        record_stage(stage, monotonic() - started, status=status)
