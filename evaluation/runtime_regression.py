"""Compare development predictions without using ground-truth or held-out data."""

from collections import Counter

import numpy as np
from scipy.optimize import linear_sum_assignment


def compare_records(reference, candidate, tolerances):
    reasons = []
    if reference["manifest_sha256"] != candidate["manifest_sha256"]:
        return ["fixture_manifest_changed"]
    if reference["model"] != candidate["model"]:
        return ["model_or_inference_settings_changed"]
    old_frames, new_frames = reference["frames"], candidate["frames"]
    if set(old_frames) != set(new_frames):
        return ["frame_set_changed"]
    for key, old in old_frames.items():
        new = new_frames[key]
        if (
            old["dimensions"] != new["dimensions"]
            or old["timestamp"] != new["timestamp"]
        ):
            reasons.append(f"{key}:frame_metadata_changed")
        old_counts = Counter(d["class"] for d in old["detections"])
        new_counts = Counter(d["class"] for d in new["detections"])
        if old_counts != new_counts:
            reasons.append(f"{key}:class_counts_changed")
        else:
            for label in old_counts:
                a = [d for d in old["detections"] if d["class"] == label]
                b = [d for d in new["detections"] if d["class"] == label]
                valid = np.array(
                    [
                        [
                            max(
                                abs(x - y)
                                for x, y in zip(left["box"], right["box"], strict=True)
                            )
                            <= tolerances["box_pixels"]
                            and abs(left["confidence"] - right["confidence"])
                            <= tolerances["confidence"]
                            for right in b
                        ]
                        for left in a
                    ],
                    dtype=bool,
                )
                rows, columns = linear_sum_assignment(~valid)
                if not valid[rows, columns].all():
                    reasons.append(f"{key}:{label}:predictions_changed")
        if old["output_sha256"] != new["output_sha256"]:
            reasons.append(f"{key}:rendered_output_changed")
    return reasons
