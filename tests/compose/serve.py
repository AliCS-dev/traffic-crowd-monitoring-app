"""Test-only API entrypoint: real services and storage, deterministic detection."""

import hashlib
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import uvicorn
from ultralytics.engine.results import Results

from app.api.application import create_app
from app.model_profile import load_runtime_model_profile


def controlled_profile():
    source = Path(__file__)
    return replace(
        load_runtime_model_profile(),
        profile_id="controlled-compose-test",
        model_id="controlled-compose-test",
        quality_gate_status="not_evaluated",
        evaluation_reference=Path("docs/testing.md"),
        checkpoint_path=Path("tests/compose/serve.py"),
        checkpoint_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        checkpoint_size_bytes=source.stat().st_size,
        device="cpu",
    )


class ControlledDetector:
    def detect(self, image, **_options):
        height, width = image.shape[:2]
        boxes = np.array(
            [[width * 0.1, height * 0.1, width * 0.4, height * 0.4, 0.9, 0]],
            dtype=np.float32,
        )
        return [Results(image, path="controlled.png", names={0: "car"}, boxes=boxes)]


def main():
    if os.getenv("CONTROLLED_COMPOSE_TEST") != "1":
        raise RuntimeError("Use only the isolated Compose test override.")
    profile = controlled_profile()
    # Patches live only in this test process; the production image is unchanged.
    with (
        patch("app.api.dependencies.load_runtime_model_profile", return_value=profile),
        patch("app.api.dependencies.verify_runtime_checkpoint"),
        patch(
            "app.api.dependencies.ObjectDetector.from_runtime_profile",
            return_value=ControlledDetector(),
        ),
    ):
        uvicorn.run(create_app(), host="0.0.0.0", port=8000, workers=1)


if __name__ == "__main__":
    main()
