"""Prepare the fixed UAVDT development sample without downloading test pixels."""

import argparse
import csv
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from zlib import crc32

import cv2
import numpy as np

from evaluation.remote_zip import HTTPRangeReader
from evaluation.uavdt_annotations import convert_uavdt_manifest, read_uavdt_boxes
from evaluation.uavdt_media_check import (
    BASE_URL,
    MEDIA_SIZE,
    MIRROR_REVISION,
    TOOLKIT_SIZE,
    read_member,
    sha256,
)
from evaluation.uavdt_readiness import (
    ANNOTATIONS_PATH,
    DATA_DIRECTORY,
    MANIFEST_PATH,
    PROTOCOL_PATH,
    PROTOCOL_VERSION,
    file_sha256,
    load_protocol,
)


def _write_verified(path: Path, payload: bytes, expected: str) -> None:
    if sha256(payload) != expected:
        raise ValueError(f"Source checksum mismatch: {path.name}")
    if path.exists():
        if file_sha256(path) != expected:
            raise ValueError(f"Cached source checksum mismatch: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def _image_payload(archive: ZipFile, name: str, path: Path) -> bytes:
    if not path.exists():
        return read_member(archive, name)
    if sum(info.filename == name for info in archive.infolist()) != 1:
        raise ValueError(f"Missing or duplicate ZIP member: {name}")
    info = archive.getinfo(name)
    if path.stat().st_size > 2_000_000:
        raise ValueError(f"Cached image exceeds member limit: {path}")
    payload = path.read_bytes()
    if len(payload) != info.file_size or crc32(payload) != info.CRC:
        raise ValueError(f"Cached image differs from archive size/CRC: {path}")
    return payload


def _record_download_attempt(output: Path, readers: tuple) -> None:
    number = len(list(output.glob("download_attempt_*.json"))) + 1
    with (output / f"download_attempt_{number:03d}.json").open(
        "x", encoding="utf-8"
    ) as handle:
        json.dump(
            [
                {
                    "url": reader.url,
                    "downloaded_bytes": reader.downloaded_bytes,
                    "ranges": reader.requests,
                }
                for reader in readers
            ],
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")


def prepare_development_data(
    root: Path, *, resume: bool = False, progress=print
) -> dict:
    root = root.resolve()
    protocol = load_protocol(root)
    output = (root / DATA_DIRECTORY).resolve()
    if not output.is_relative_to(root):
        raise ValueError("Output escapes the repository")
    if resume and any(
        (root / path).exists() for path in (MANIFEST_PATH, ANNOTATIONS_PATH)
    ):
        raise ValueError(
            "Resume is only for acquisition, not an already converted dataset"
        )
    output.mkdir(parents=True, exist_ok=resume)
    cached_images = len(list(output.glob("images/*/*.jpg")))
    attrs_zip = root / "data/evaluation/raw/source_inspection_20261007/uavdt/M_attr.zip"
    if file_sha256(attrs_zip) != protocol["attribute_zip_sha256"]:
        raise ValueError("Retained attribute ZIP checksum mismatch")
    with ZipFile(attrs_zip) as archive:
        for item in protocol["sequences"]:
            if item["source_split"] != "train":
                raise ValueError("Preparation accepts training sequences only")
            _write_verified(
                output / "attributes/train" / f"{item['sequence']}_attr.txt",
                read_member(archive, item["attribute_member"]),
                item["attribute_sha256"],
            )

    toolkit = HTTPRangeReader(
        f"{BASE_URL}/UAV-benchmark-MOTD_v1.0.zip",
        TOOLKIT_SIZE,
        byte_budget=32_000_000,
    )
    media = HTTPRangeReader(
        f"{BASE_URL}/UAV-benchmark-M.zip",
        MEDIA_SIZE,
        byte_budget=384_000_000,
    )
    records = []
    with ExitStack() as stack:
        stack.callback(_record_download_attempt, output, (toolkit, media))
        annotations = stack.enter_context(ZipFile(toolkit))
        images = stack.enter_context(ZipFile(media))
        for item in protocol["sequences"]:
            sequence = item["sequence"]
            progress(f"Preparing {sequence}: {len(item['frames'])} training frames.")
            for suffix, field in (
                ("whole", "detection_sha256"),
                ("ignore", "ignore_sha256"),
            ):
                name = f"UAV-benchmark-MOTD_v1.0/GT/{sequence}_gt_{suffix}.txt"
                path = output / "GT" / Path(name).name
                payload = (
                    path.read_bytes()
                    if path.exists()
                    else read_member(annotations, name, limit=8_000_000)
                )
                _write_verified(
                    path,
                    payload,
                    item[field],
                )
            boxes = read_uavdt_boxes(output / "GT" / f"{sequence}_gt_whole.txt")
            frames = {box.frame for box in boxes}
            if frames != set(range(1, item["last_labelled_frame"] + 1)):
                raise ValueError(f"Labelled frame coverage changed: {sequence}")
            for frame in item["frames"]:
                name = f"UAV-benchmark-M/{sequence}/img{frame:06d}.jpg"
                path = output / "images" / sequence / Path(name).name
                payload = _image_payload(images, name, path)
                image = cv2.imdecode(
                    np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR
                )
                if image is None:
                    raise ValueError(f"Unreadable image: {name}")
                height, width = image.shape[:2]
                digest = sha256(payload)
                _write_verified(path, payload, digest)
                records.append(
                    {
                        "asset_id": f"uavdt_{sequence}_{frame:06d}",
                        "dataset_version": PROTOCOL_VERSION,
                        "collection_id": "uavdt",
                        "source_group_id": sequence,
                        "dataset_role": "validation",
                        "source_split": "train",
                        "evaluation_image_path": path.relative_to(root).as_posix(),
                        "width": width,
                        "height": height,
                        "target_classes": "car_or_van;bus;truck",
                        "annotation_type": "bounding_box",
                        "canonical_annotation_path": ANNOTATIONS_PATH.as_posix(),
                        "frame_number": frame,
                        "image_sha256": digest,
                    }
                )
    if len({row["image_sha256"] for row in records}) != len(records):
        raise ValueError("Exact duplicate images; no automatic frame replacement")
    with (root / MANIFEST_PATH).open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    converted = convert_uavdt_manifest(
        repository_root=root,
        manifest_path=MANIFEST_PATH,
        gt_directory=DATA_DIRECTORY / "GT",
        attributes_directory=DATA_DIRECTORY / "attributes",
        role="validation",
        output_path=ANNOTATIONS_PATH,
    )
    images_by_id = {image["id"]: image for image in converted["images"]}
    categories = {item["id"]: item["name"] for item in converted["categories"]}
    counts = Counter(categories[box["category_id"]] for box in converted["annotations"])
    sequence_counts = {}
    out_of_bounds = []
    inside_ignore = []
    for box in converted["annotations"]:
        image = images_by_id[box["image_id"]]
        counts_for_sequence = sequence_counts.setdefault(
            image["source_group_id"], Counter()
        )
        counts_for_sequence[categories[box["category_id"]]] += 1
        x, y, width, height = box["bbox"]
        identity = {
            "asset_id": image["asset_id"],
            "track_id": box["source_attributes"]["track_id"],
        }
        if x < 0 or y < 0 or x + width > image["width"] or y + height > image["height"]:
            out_of_bounds.append(identity)
        for region in converted["ignored_regions"]:
            if region["image_id"] != box["image_id"]:
                continue
            rx, ry, rw, rh = region["bbox"]
            if rx < x and ry < y and x + width < rx + rw and y + height < ry + rh:
                inside_ignore.append(identity)
                break
    report = {
        "schema_version": 1,
        "record_type": "prepared_source_label_development_data_not_accuracy",
        "protocol_sha256": file_sha256(root / PROTOCOL_PATH),
        "manifest_sha256": file_sha256(root / MANIFEST_PATH),
        "canonical_sha256": file_sha256(root / ANNOTATIONS_PATH),
        "mirror_revision": MIRROR_REVISION,
        "images": len(records),
        "sequences": len(protocol["sequences"]),
        "box_counts": dict(counts),
        "per_sequence_box_counts": sequence_counts,
        "ignored_regions": len(converted["ignored_regions"]),
        "out_of_bounds_boxes": out_of_bounds,
        "ground_truth_strictly_inside_ignore": inside_ignore,
        "occlusion_code_counts": dict(
            Counter(
                str(b["source_attributes"]["occlusion_code"])
                for b in converted["annotations"]
            )
        ),
        "duplicate_image_hashes": 0,
        "human_annotation_review": False,
        "model_inference_run": False,
        "test_media_downloaded": False,
        "cached_images_at_attempt_start": cached_images,
        "download_accounting": (
            "Successful payload bytes in this attempt only; "
            "previous attempts are logged separately when available"
        ),
        "downloads": [
            {
                "url": reader.url,
                "byte_budget": reader.byte_budget,
                "downloaded_bytes": reader.downloaded_bytes,
                "requests": len(reader.requests),
            }
            for reader in (toolkit, media)
        ],
    }
    for filename, payload in (
        ("preparation.json", report),
        (
            "download_ranges.json",
            {"toolkit": toolkit.requests, "media": media.requests},
        ),
    ):
        with (output / filename).open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse verified files from an incomplete acquisition",
    )
    args = parser.parse_args()
    try:
        report = prepare_development_data(args.repository_root, resume=args.resume)
    except (OSError, ValueError, KeyError, BadZipFile, cv2.error) as error:
        parser.exit(1, f"UAVDT preparation failed: {error}\n")
    print(
        f"Prepared {report['images']} training-source frames; "
        "no inference or test pixels."
    )
    print(f"Preparation record: {DATA_DIRECTORY / 'preparation.json'}")


if __name__ == "__main__":
    main()
