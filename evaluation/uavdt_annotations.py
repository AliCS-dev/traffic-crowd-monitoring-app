"""Convert selected UAVDT DET frames without changing the historical dataset."""

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from evaluation.annotation_conversion import PROJECT_CATEGORIES
from evaluation.evaluation_config import DATASET_ROLES
from evaluation.evaluation_data import (
    MANIFEST_FIELDS,
    UAVDT_IGNORE_POLICY,
    BoundingBox,
    parse_target_classes,
)

CLASS_IDS = {1: 4, 2: 6, 3: 5}
TARGET_CLASSES = frozenset({"car_or_van", "truck", "bus"})
OUT_OF_VIEW = {1: "none", 2: "medium", 3: "small"}
OCCLUSION = {1: "none", 2: "large", 3: "medium", 4: "small"}
SEQUENCE_ATTRIBUTES = (
    "daylight",
    "night",
    "fog",
    "low_altitude",
    "medium_altitude",
    "high_altitude",
    "front_view",
    "side_view",
    "bird_view",
    "long_term",
)


@dataclass(frozen=True)
class UAVDTBox:
    frame: int
    track_id: int
    box: BoundingBox
    out_of_view: int
    occlusion: int
    category: int

    def source_attributes(self) -> dict:
        return {
            "frame_number": self.frame,
            "track_id": self.track_id,
            "source_category_id": self.category,
            "out_of_view_code": self.out_of_view,
            "occlusion_code": self.occlusion,
            "out_of_view": OUT_OF_VIEW.get(self.out_of_view),
            "occlusion": OCCLUSION.get(self.occlusion),
        }


def read_uavdt_boxes(path: Path, *, ignored: bool = False) -> tuple[UAVDTBox, ...]:
    suffix = "_gt_ignore.txt" if ignored else "_gt_whole.txt"
    if not re.fullmatch(r"M\d{4}" + re.escape(suffix), path.name):
        raise ValueError(f"Expected a UAVDT DET {suffix} file, not MOT: {path}")
    boxes = []
    identities = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for line_number, fields in enumerate(csv.reader(handle), start=1):
            if not fields:
                continue
            try:
                if len(fields) != 9:
                    raise ValueError("Expected nine integer fields")
                frame, track, x, y, width, height, outside, occlusion, category = map(
                    int, fields
                )
                if frame < 1 or track < 1:
                    raise ValueError("Frame and track IDs must be positive (1-based)")
                if (frame, track) in identities:
                    raise ValueError("Duplicate frame/track identity")
                if ignored:
                    if (outside, occlusion, category) != (1, -1, -1):
                        raise ValueError("Unknown ignored-region sentinel fields")
                elif (
                    outside not in OUT_OF_VIEW
                    or occlusion not in OCCLUSION
                    or category not in CLASS_IDS
                ):
                    raise ValueError("Unknown category or source attribute code")
                boxes.append(
                    UAVDTBox(
                        frame,
                        track,
                        BoundingBox(x, y, width, height),
                        outside,
                        occlusion,
                        category,
                    )
                )
                identities.add((frame, track))
            except ValueError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    if not boxes and not ignored:
        raise ValueError(f"DET ground truth is empty: {path}")
    return tuple(boxes)


def read_sequence_attributes(directory: Path) -> dict[str, dict]:
    sequences = {}
    for split in ("train", "test"):
        for path in sorted((directory / split).glob("*_attr.txt")):
            # The release contains 'M0701 _attr.txt'; retain the original path below.
            sequence = path.name.removesuffix("_attr.txt").strip()
            if not re.fullmatch(r"M\d{4}", sequence) or sequence in sequences:
                raise ValueError(
                    f"Invalid or duplicate sequence attribute file: {path}"
                )
            with path.open(encoding="utf-8", newline="") as handle:
                rows = [row for row in csv.reader(handle) if row]
            if len(rows) != 1 or len(rows[0]) != 10:
                raise ValueError(f"Expected ten binary sequence attributes: {path}")
            flags = [int(value) for value in rows[0]]
            if any(flag not in (0, 1) for flag in flags):
                raise ValueError(f"Sequence attributes must be binary: {path}")
            sequences[sequence] = {
                "split": split,
                "attributes": dict(zip(SEQUENCE_ATTRIBUTES, flags, strict=True)),
                "path": path,
            }
    if not sequences:
        raise ValueError(f"No sequence attribute files found in: {directory}")
    return sequences


def _relative_path(root: Path, value: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Expected a repository-relative path: {value!r}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes repository: {value}")
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert_uavdt_manifest(
    *,
    repository_root: Path,
    manifest_path: Path,
    gt_directory: Path,
    attributes_directory: Path,
    role: str,
    output_path: Path,
) -> dict:
    """Require an explicit selection and verified media; never infer negative frames."""
    if role not in DATASET_ROLES:
        raise ValueError(f"Unknown dataset role: {role}")
    root = repository_root.resolve()
    manifest = _relative_path(root, str(manifest_path))
    output = _relative_path(root, str(output_path))
    gt_root = _relative_path(root, str(gt_directory))
    attrs_root = _relative_path(root, str(attributes_directory))
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite annotations: {output}")
    with manifest.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = MANIFEST_FIELDS | {"frame_number", "source_split", "image_sha256"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("UAVDT selection manifest is missing required fields")
        records = list(reader)
    if not records or len({r["dataset_version"] for r in records}) != 1:
        raise ValueError("Manifest must contain one nonempty dataset version")
    version = records[0]["dataset_version"]
    if not version.startswith("uavdt-"):
        raise ValueError("Use a separate dataset version beginning with 'uavdt-'")
    sequences = read_sequence_attributes(attrs_root)
    asset_ids = set()
    frame_ids = set()
    sequence_roles: dict[str, set[str]] = defaultdict(set)
    for record in records:
        sequence = record["source_group_id"]
        metadata = sequences.get(sequence)
        if metadata is None:
            raise ValueError(f"No attributes for sequence: {sequence}")
        flags = metadata["attributes"]
        if (flags["daylight"], flags["night"], flags["fog"]) != (1, 0, 0):
            raise ValueError(f"Sequence is outside the daytime subset: {sequence}")
        source_split = metadata["split"]
        allowed_roles = (
            {"held_out_test"} if source_split == "test" else {"training", "validation"}
        )
        if (
            record["source_split"] != source_split
            or record["dataset_role"] not in allowed_roles
        ):
            raise ValueError(f"Source split/role mismatch: {sequence}")
        if (
            record["collection_id"] != "uavdt"
            or record["annotation_type"] != "bounding_box"
            or parse_target_classes(record["target_classes"]) != TARGET_CLASSES
        ):
            raise ValueError(
                "UAVDT requires car_or_van, bus and truck box targets only"
            )
        frame = int(record["frame_number"])
        identity = (sequence, frame)
        if (
            frame < 1
            or not record["asset_id"]
            or record["asset_id"] in asset_ids
            or identity in frame_ids
        ):
            raise ValueError("Invalid or duplicate asset/frame identity")
        asset_ids.add(record["asset_id"])
        frame_ids.add(identity)
        sequence_roles[sequence].add(record["dataset_role"])
    if any(len(roles) > 1 for roles in sequence_roles.values()):
        raise ValueError("A source sequence cannot cross dataset roles")
    selected = sorted(
        (record for record in records if record["dataset_role"] == role),
        key=lambda record: record["asset_id"],
    )
    if not selected:
        raise ValueError(f"Manifest contains no selected assets for role: {role}")
    images, annotations, regions, sources = [], [], [], []
    cache = {}
    for image_id, record in enumerate(selected, start=1):
        if _relative_path(root, record["canonical_annotation_path"]) != output:
            raise ValueError("Selected annotation path must match the output path")
        sequence = record["source_group_id"]
        metadata = sequences[sequence]
        if sequence not in cache:
            gt_path = gt_root / f"{sequence}_gt_whole.txt"
            ignore_path = gt_root / f"{sequence}_gt_ignore.txt"
            boxes = read_uavdt_boxes(gt_path)
            ignored = read_uavdt_boxes(ignore_path, ignored=True)
            by_frame, ignores_by_frame = defaultdict(list), defaultdict(list)
            for box in boxes:
                by_frame[box.frame].append(box)
            for box in ignored:
                ignores_by_frame[box.frame].append(box)
            cache[sequence] = by_frame, ignores_by_frame
            for path in (gt_path, ignore_path, metadata["path"]):
                sources.append(
                    {"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}
                )
        boxes_by_frame, ignores_by_frame = cache[sequence]
        frame = int(record["frame_number"])
        if frame not in boxes_by_frame:
            raise ValueError(f"Selected frame has no DET labels: {sequence}/{frame}")
        image_path = _relative_path(root, record["evaluation_image_path"])
        image_bytes = image_path.read_bytes()
        actual_hash = hashlib.sha256(image_bytes).hexdigest()
        if actual_hash != record["image_sha256"]:
            raise ValueError(f"Image checksum mismatch: {image_path}")
        if not image_bytes:
            raise ValueError(f"Image is empty: {image_path}")
        image = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        width, height = int(record["width"]), int(record["height"])
        if image is None or image.shape[:2] != (height, width):
            raise ValueError(f"Image dimensions/readability mismatch: {image_path}")
        images.append(
            {
                "id": image_id,
                "asset_id": record["asset_id"],
                "file_name": record["evaluation_image_path"],
                "width": width,
                "height": height,
                "sha256": actual_hash,
                "source_group_id": sequence,
                "source_split": metadata["split"],
                "frame_number": frame,
                "source_attributes": metadata["attributes"],
            }
        )
        for box in boxes_by_frame[frame]:
            annotations.append(
                {
                    "id": len(annotations) + 1,
                    "image_id": image_id,
                    "category_id": CLASS_IDS[box.category],
                    "bbox": list(box.box.as_xywh()),
                    "area": box.box.width * box.box.height,
                    "iscrowd": 0,
                    "source_attributes": box.source_attributes(),
                }
            )
        for box in ignores_by_frame[frame]:
            regions.append(
                {
                    "id": len(regions) + 1,
                    "image_id": image_id,
                    "bbox": list(box.box.as_xywh()),
                    "source_attributes": box.source_attributes(),
                }
            )
    result = {
        "info": {
            "description": "UAVDT daytime subset; not official challenge scores",
            "version": version,
            "dataset_role": role,
            "coordinate_policy": "source_xywh_unmodified",
            "selection_manifest_sha256": _sha256(manifest),
            "source_files": sources,
        },
        "ignore_policy": UAVDT_IGNORE_POLICY,
        "images": images,
        "annotations": annotations,
        "ignored_regions": regions,
        "categories": [
            item for item in PROJECT_CATEGORIES if item["name"] in TARGET_CLASSES
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--gt-directory", type=Path, required=True)
    parser.add_argument("--attributes-directory", type=Path, required=True)
    parser.add_argument("--role", choices=DATASET_ROLES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = convert_uavdt_manifest(
            repository_root=args.repository_root,
            manifest_path=args.manifest,
            gt_directory=args.gt_directory,
            attributes_directory=args.attributes_directory,
            role=args.role,
            output_path=args.output,
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"UAVDT conversion failed: {error}\n")
    print(
        f"Converted {len(result['images'])} frames, "
        f"{len(result['annotations'])} boxes and "
        f"{len(result['ignored_regions'])} ignored regions."
    )


if __name__ == "__main__":
    main()
