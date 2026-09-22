"""Prepare a small CC-BY-4.0 development fixture from verified validation media."""

import csv
import hashlib
import json
import shutil
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "data/runtime-regression/fixtures"
SOURCE_IDS = [f"traffic_roundabout_near_3_f{number:06}" for number in (6, 18, 29)]


def main():
    with (ROOT / "data/evaluation/manifest.csv").open() as handle:
        rows = {row["asset_id"]: row for row in csv.DictReader(handle)}
    frames = []
    sources = []
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for asset_id in SOURCE_IDS:
        row = rows[asset_id]
        if row["dataset_role"] != "validation" or row["license_id"] != "CC-BY-4.0":
            raise ValueError("Regression media must remain licensed development data.")
        path = ROOT / row["evaluation_image_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["image_sha256"]:
            raise ValueError(f"Source checksum mismatch: {asset_id}")
        frame = cv2.imread(str(path))
        if frame is None or frame.shape[:2] != (720, 1280):
            raise ValueError("Unexpected source dimensions.")
        frames.append(frame)
        sources.append(
            {
                key: row[key]
                for key in (
                    "asset_id",
                    "source_group_id",
                    "dataset_role",
                    "source_url",
                    "license_id",
                    "license_url",
                    "image_sha256",
                )
            }
        )
    for index, number in ((0, 6), (2, 29)):
        shutil.copyfile(
            ROOT / rows[SOURCE_IDS[index]]["evaluation_image_path"],
            DESTINATION / f"roundabout_{number}.png",
        )
    video = DESTINATION / "roundabout_sequence.avi"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (1280, 720)
    )
    if not writer.isOpened():
        raise RuntimeError("MJPEG encoder unavailable.")
    try:
        for frame in frames:
            for _ in range(10):
                writer.write(frame)
    finally:
        writer.release()
    fixtures = []
    for name, kind, mime in (
        ("roundabout_6.png", "image", "image/png"),
        ("roundabout_29.png", "image", "image/png"),
        ("roundabout_sequence.avi", "video", "video/x-msvideo"),
    ):
        path = DESTINATION / name
        fixtures.append(
            {
                "name": name,
                "kind": kind,
                "mime": mime,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema_version": 1,
        "purpose": "development regression, not accuracy",
        "sources": sources,
        "fixtures": fixtures,
        "sampling_interval_seconds": 1,
        "tolerances": {
            "box_pixels": 0.5,
            "confidence": 0.0001,
            "class_counts": "exact",
            "rendered_sha256": "exact",
        },
        "video_transformation": (
            "Each source image repeated 10 times at 10 fps, MJPEG. "
            "Artificial timeline, not original capture timing."
        ),
    }
    (DESTINATION.parent / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(f"Prepared {len(fixtures)} fixtures in {DESTINATION}")


if __name__ == "__main__":
    main()
