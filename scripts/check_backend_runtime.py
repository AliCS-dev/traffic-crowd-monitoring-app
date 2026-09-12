"""Verify the mounted runtime checkpoint and run one synthetic-image inference."""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch

from app.api.settings import ApiSettings
from app.model_profile import load_runtime_model_profile, verify_runtime_checkpoint
from app.services.detection_service import ObjectDetector, detect_objects_with_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-cuda", action="store_true")
    arguments = parser.parse_args()
    settings = ApiSettings.from_environment()
    profile = load_runtime_model_profile()
    if settings.model_device is not None:
        profile = replace(profile, device=settings.model_device)
    if arguments.require_cuda and (
        not profile.device.startswith("cuda") or not torch.cuda.is_available()
    ):
        raise RuntimeError("A CUDA device is required for this check.")
    checkpoint = verify_runtime_checkpoint(profile)
    detector = ObjectDetector(checkpoint)
    results = detect_objects_with_profile(
        np.zeros((640, 640, 3), dtype=np.uint8), detector, profile
    )
    if len(results) != 1:
        raise RuntimeError("Expected one inference result.")
    print(
        json.dumps(
            {
                "status": "ok",
                "torch": torch.__version__,
                "cuda_runtime": torch.version.cuda,
                "cuda_available": torch.cuda.is_available(),
                "device": profile.device,
                "model_id": profile.model_id,
                "checkpoint_sha256": profile.checkpoint_sha256,
                "quality_gate_status": profile.quality_gate_status,
                "check": "synthetic image inference, not an accuracy evaluation",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
