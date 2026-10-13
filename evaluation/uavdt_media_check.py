"""Bounded training-only media/label inspection, not a model evaluation."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import cv2
import numpy as np

from evaluation.annotation_preview import (
    CATEGORY_COLOURS,
    CATEGORY_NAMES,
    box_quality_flags,
)
from evaluation.evaluation_config import DatasetSettings
from evaluation.evaluation_data import load_evaluation_dataset
from evaluation.remote_zip import HTTPRangeReader
from evaluation.uavdt_annotations import (
    convert_uavdt_manifest,
    read_sequence_attributes,
    read_uavdt_boxes,
)

MIRROR_REVISION = "ad1cfbe161c183cfdee26f6c42c6fff6552a54dc"
BASE_URL = f"https://huggingface.co/datasets/vanthanh/UAVDT-Benchmark-M/resolve/{MIRROR_REVISION}"
MEDIA_SIZE = 6_790_452_113
TOOLKIT_SIZE = 245_719_325
SEQUENCES = ("M0101", "M0210", "M0702")
DEFAULT_OUTPUT = Path("data/evaluation/raw/uavdt_media_check_20261013")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selected_frames(frame_ids: set[int]) -> tuple[int, ...]:
    if not frame_ids or min(frame_ids) != 1 or max(frame_ids) != len(frame_ids):
        raise ValueError("Inspection requires contiguous labelled frames starting at 1")
    return tuple(sorted({1, (max(frame_ids) + 1) // 2, max(frame_ids)}))


def require_training_daytime(metadata: dict) -> None:
    flags = metadata["attributes"]
    if metadata["split"] != "train" or (
        flags["daylight"],
        flags["night"],
        flags["fog"],
    ) != (1, 0, 0):
        raise ValueError("Media inspection accepts daytime training sequences only")


def read_member(archive: ZipFile, name: str, limit: int = 2_000_000) -> bytes:
    if sum(info.filename == name for info in archive.infolist()) != 1:
        raise ValueError(f"Missing or duplicate ZIP member: {name}")
    info = archive.getinfo(name)
    if info.is_dir() or info.file_size > limit or info.compress_size > limit:
        raise ValueError(f"ZIP member exceeds inspection limit: {name}")
    return archive.read(info)  # zipfile also verifies the member's CRC.


def render_overlay(
    image: np.ndarray, annotations: list[dict], regions: list[dict]
) -> np.ndarray:
    """Keep the image at native resolution and put the legend outside it."""
    canvas = image.copy()
    for region in regions:
        x, y, w, h = region["bbox"]
        cv2.rectangle(
            canvas, (round(x), round(y)), (round(x + w), round(y + h)), (255, 0, 255), 2
        )
    for annotation in annotations:
        x, y, w, h = annotation["bbox"]
        cv2.rectangle(
            canvas,
            (round(x), round(y)),
            (round(x + w), round(y + h)),
            CATEGORY_COLOURS[annotation["category_id"]],
            1,
        )
    banner = np.full((45, image.shape[1], 3), 245, dtype=np.uint8)
    x = 10
    labels = [(CATEGORY_NAMES[c], CATEGORY_COLOURS[c]) for c in (4, 6, 5)]
    for label, colour in [*labels, ("ignored region", (255, 0, 255))]:
        cv2.putText(banner, label, (x, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)
        x += 220
    return np.vstack((canvas, banner))


def check_media(root: Path, output_relative: Path = DEFAULT_OUTPUT) -> dict:
    root = root.resolve()
    if (
        output_relative.is_absolute()
        or ".." in output_relative.parts
        or output_relative.parts[:3] != ("data", "evaluation", "raw")
    ):
        raise ValueError(
            "Inspection output must be a new data/evaluation/raw directory"
        )
    output = (root / output_relative).resolve()
    if not output.is_relative_to(root):
        raise ValueError("Inspection output escapes repository")
    output.mkdir(parents=True, exist_ok=False)
    retained = root / "data/evaluation/raw/source_inspection_20261007/uavdt"
    evidence = json.loads(
        (root / "data/evaluation/annotation_feasibility_v2.json").read_text()
    )
    source_rows = {row["sequence"]: row for row in evidence["uavdt"]["sequences"]}
    attrs_zip = retained / "M_attr.zip"
    if sha256(attrs_zip.read_bytes()) != evidence["uavdt"]["attribute_zip_sha256"]:
        raise ValueError("Retained attribute ZIP checksum mismatch")
    with ZipFile(attrs_zip) as archive:
        for sequence in SEQUENCES:
            record = source_rows[sequence]
            if record["source_split"] != "train":
                raise ValueError("Held-out sequence requested")
            payload = read_member(archive, record["attribute_member"])
            if sha256(payload) != record["attribute_sha256"]:
                raise ValueError("Sequence attribute checksum mismatch")
            path = output / "attributes/train" / f"{sequence}_attr.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    metadata = read_sequence_attributes(output / "attributes")
    for sequence in SEQUENCES:
        require_training_daytime(metadata[sequence])
    toolkit = HTTPRangeReader(
        f"{BASE_URL}/UAV-benchmark-MOTD_v1.0.zip", TOOLKIT_SIZE, byte_budget=8_000_000
    )
    media = HTTPRangeReader(f"{BASE_URL}/UAV-benchmark-M.zip", MEDIA_SIZE)
    records, member_evidence = [], []
    canonical_path = output_relative / "instances_training.json"
    with ZipFile(toolkit) as annotations, ZipFile(media) as images:
        for sequence in SEQUENCES:
            for suffix, field in (
                ("whole", "detection_sha256"),
                ("ignore", "ignore_sha256"),
            ):
                name = f"UAV-benchmark-MOTD_v1.0/GT/{sequence}_gt_{suffix}.txt"
                payload = read_member(annotations, name)
                if sha256(payload) != source_rows[sequence][field]:
                    raise ValueError(
                        f"Annotation differs from retained inspection: {name}"
                    )
                path = output / "GT" / Path(name).name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(payload)
            boxes = read_uavdt_boxes(output / "GT" / f"{sequence}_gt_whole.txt")
            for frame in selected_frames({box.frame for box in boxes}):
                name = f"UAV-benchmark-M/{sequence}/img{frame:06d}.jpg"
                payload = read_member(images, name)
                image = cv2.imdecode(
                    np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR
                )
                if image is None:
                    raise ValueError(f"Unreadable image: {name}")
                height, width = image.shape[:2]
                path = output / "images" / sequence / Path(name).name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                asset_id = f"uavdt_{sequence}_{frame:06d}"
                records.append(
                    {
                        "asset_id": asset_id,
                        "dataset_version": "uavdt-media-check-v1",
                        "collection_id": "uavdt",
                        "source_group_id": sequence,
                        "dataset_role": "training",
                        "source_split": "train",
                        "evaluation_image_path": path.relative_to(root).as_posix(),
                        "width": width,
                        "height": height,
                        "target_classes": "car_or_van;bus;truck",
                        "annotation_type": "bounding_box",
                        "canonical_annotation_path": canonical_path.as_posix(),
                        "frame_number": frame,
                        "image_sha256": sha256(payload),
                    }
                )
                member_evidence.append(
                    {
                        "asset_id": asset_id,
                        "zip_member": name,
                        "bytes": len(payload),
                        "sha256": sha256(payload),
                        "zip_crc32": f"{images.getinfo(name).CRC:08x}",
                    }
                )
    manifest_path = output_relative / "manifest.csv"
    with (root / manifest_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    converted = convert_uavdt_manifest(
        repository_root=root,
        manifest_path=manifest_path,
        gt_directory=output_relative / "GT",
        attributes_directory=output_relative / "attributes",
        role="training",
        output_path=canonical_path,
    )
    dataset = load_evaluation_dataset(
        root, DatasetSettings("uavdt-media-check-v1", "training", manifest_path)
    )
    frames = []
    (output / "overlays").mkdir()
    for record, member, image_record in zip(
        records, member_evidence, converted["images"], strict=True
    ):
        # Both the manifest and converter order use the same sorted asset IDs.
        if record["asset_id"] != image_record["asset_id"]:
            raise ValueError("Image/manifest ordering mismatch")
        boxes = [
            a for a in converted["annotations"] if a["image_id"] == image_record["id"]
        ]
        regions = [
            a
            for a in converted["ignored_regions"]
            if a["image_id"] == image_record["id"]
        ]
        image = cv2.imread(str(root / record["evaluation_image_path"]))
        overlay = render_overlay(image, boxes, regions)
        preview = output / "overlays" / f"{record['asset_id']}.png"
        if not cv2.imwrite(str(preview), overlay):
            raise ValueError(f"Cannot write overlay: {preview}")
        ignored = [
            r for r in dataset.ignored_regions if r.asset_id == record["asset_id"]
        ]
        ground_truth = [
            b for b in dataset.ground_truth_boxes if b.asset_id == record["asset_id"]
        ]
        frames.append(
            {
                **record,
                **member,
                "box_counts": dict(
                    Counter(CATEGORY_NAMES[b["category_id"]] for b in boxes)
                ),
                "ignore_regions": len(regions),
                "quality_flags": box_quality_flags(
                    boxes, record["width"], record["height"]
                ),
                "out_of_bounds_boxes": sum(
                    b.box.x < 0
                    or b.box.y < 0
                    or b.box.x + b.box.width > record["width"]
                    or b.box.y + b.box.height > record["height"]
                    for b in ground_truth
                ),
                "gt_strictly_inside_ignore": sum(
                    any(r.contains(b.box) for r in ignored) for b in ground_truth
                ),
                "overlay_path": preview.relative_to(root).as_posix(),
                "overlay_sha256": sha256(preview.read_bytes()),
            }
        )
    report = {
        "record_type": "uavdt_training_media_compatibility_not_accuracy",
        "mirror_revision": MIRROR_REVISION,
        "selection_rule": (
            "M0101/M0210/M0702 training only; first/middle/last labelled frame"
        ),
        "selection_purpose": (
            "front/side and bird views, vehicle classes, empty/nonempty ignores"
        ),
        "test_media_downloaded": False,
        "model_inference_run": False,
        "human_annotation_review": False,
        "original_publisher_equivalence_verified": False,
        "manifest_sha256": sha256((root / manifest_path).read_bytes()),
        "canonical_sha256": sha256((root / canonical_path).read_bytes()),
        "canonical_source_files": converted["info"]["source_files"],
        "duplicate_image_hashes": len(records)
        - len({r["image_sha256"] for r in records}),
        "frames": frames,
        "downloads": [
            {
                "url": reader.url,
                "archive_bytes": reader.size,
                "downloaded_bytes": reader.downloaded_bytes,
                "ranges": reader.requests,
            }
            for reader in (toolkit, media)
        ],
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        result = check_media(args.repository_root, args.output_directory)
    except (OSError, ValueError, BadZipFile, cv2.error) as error:
        parser.exit(1, f"Media check failed: {error}\n")
    print(
        f"Checked {len(result['frames'])} training frames; no inference or test media."
    )
    print(f"Local report and overlays: {args.output_directory}")


if __name__ == "__main__":
    main()
