"""Readiness for a fixed UAVDT source-label baseline, not a quality-gate pass."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from evaluation.evaluation_config import EvaluationConfig, load_evaluation_config
from evaluation.evaluation_data import UAVDT_IGNORE_POLICY, load_evaluation_dataset
from evaluation.uavdt_annotations import build_uavdt_annotations

PROTOCOL_VERSION = "uavdt-daytime-source-labels-v1"
CONFIG_PATH = Path("configs/evaluation/uavdt_daytime_baseline.json")
PROTOCOL_PATH = Path("data/evaluation/uavdt_daytime_protocol.json")
PREPARATION_PATH = Path("data/evaluation/uavdt_daytime_preparation.json")
EVIDENCE_PATH = Path("data/evaluation/annotation_feasibility_v2.json")
EVIDENCE_SHA256 = "7867bc129eb464b248d1a0d68d8d104a03049bc826186f699606261e599b7c75"
CHECKPOINT_SHA256 = "e57204b8d77b5b22ea9253cbd5664b707623aeb7c19dbaa9034fe5a60bed6571"
DATA_DIRECTORY = Path("data/evaluation/raw/uavdt_daytime_v1")
MANIFEST_PATH = DATA_DIRECTORY / "manifest.csv"
ANNOTATIONS_PATH = DATA_DIRECTORY / "instances_validation.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evenly_spaced_frames(last_frame: int, count: int = 10) -> list[int]:
    if count < 2 or last_frame < count:
        raise ValueError("Sampling requires at least two distinct labelled frames")
    return [1 + index * (last_frame - 1) // (count - 1) for index in range(count)]


def build_protocol(root: Path) -> dict:
    if file_sha256(root / EVIDENCE_PATH) != EVIDENCE_SHA256:
        raise ValueError("Source inventory checksum differs from the frozen inventory")
    evidence = json.loads((root / EVIDENCE_PATH).read_text(encoding="utf-8"))["uavdt"]
    sequences = []
    reserved = []
    for row in sorted(evidence["sequences"], key=lambda item: item["sequence"]):
        if not row["daylight_only"]:
            continue
        if row["source_split"] == "test":
            reserved.append(row["sequence"])
            continue
        if row["source_split"] != "train" or (
            row["frame_min"] != 1 or row["annotated_frames"] != row["frame_max"]
        ):
            raise ValueError("Expected contiguous training labels starting at frame 1")
        sequences.append(
            {
                "sequence": row["sequence"],
                "source_split": "train",
                "frames": evenly_spaced_frames(row["frame_max"]),
                "last_labelled_frame": row["frame_max"],
                "attribute_member": row["attribute_member"],
                **{
                    field: row[field]
                    for field in (
                        "attribute_sha256",
                        "detection_sha256",
                        "ignore_sha256",
                    )
                },
            }
        )
    if len(sequences) != 17 or len(reserved) != 12:
        raise ValueError("Frozen inventory must contain 17 training/12 test sequences")
    return {
        "schema_version": 1,
        "protocol_version": PROTOCOL_VERSION,
        "record_type": "development_source_label_protocol_not_accuracy",
        "dataset_role": "validation",
        "selection_rule": (
            "ten frames per daytime training sequence: 1 + floor(i*(N-1)/9), i=0..9"
        ),
        "label_policy": (
            "retain_all_native_DET_boxes_and_occlusion_codes_without_corrections"
        ),
        "ignore_policy": UAVDT_IGNORE_POLICY,
        "target_classes": ["car_or_van", "bus", "truck"],
        "source_inventory_sha256": EVIDENCE_SHA256,
        "attribute_zip_sha256": evidence["attribute_zip_sha256"],
        "baseline_config_sha256": file_sha256(root / CONFIG_PATH),
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "sequences": sequences,
        "reserved_test_sequences": reserved,
        "known_label_concerns": [
            {
                "sequence": "M0210",
                "frame": 583,
                "track_id": 34,
                "observation": (
                    "Large car box over vegetation/road; target not identifiable"
                ),
                "decision": "retain_native_label",
            },
            {
                "sequence": "M0210",
                "frame": 583,
                "track_id": 18,
                "observation": (
                    "Box over toll canopy; target not identifiable in the still image"
                ),
                "decision": "retain_native_label",
            },
        ],
        "human_annotation_review": False,
        "official_publisher_equivalence_verified": False,
        "independent_locations_verified": False,
        "final_holdout_authorized": False,
        "model_adoption_authorized": False,
    }


def load_protocol(root: Path) -> dict:
    protocol = json.loads((root / PROTOCOL_PATH).read_text(encoding="utf-8"))
    if protocol != build_protocol(root):
        raise ValueError("Frozen UAVDT protocol/configuration has changed")
    return protocol


def validate_uavdt_evaluation(root: Path, config: EvaluationConfig) -> dict:
    """Verify actual media and native labels before any hardware/model work."""
    root = root.resolve()
    protocol = load_protocol(root)
    expected_config = load_evaluation_config(root / CONFIG_PATH)
    if config != expected_config or (
        config.protocol_version != PROTOCOL_VERSION
        or config.dataset.role != "validation"
        or config.dataset.version != PROTOCOL_VERSION
        or config.dataset.manifest_path != MANIFEST_PATH
    ):
        raise ValueError("Only the frozen UAVDT development baseline is authorized")
    preparation = json.loads((root / PREPARATION_PATH).read_text(encoding="utf-8"))
    expected_hashes = {
        "protocol_sha256": file_sha256(root / PROTOCOL_PATH),
        "manifest_sha256": file_sha256(root / MANIFEST_PATH),
        "canonical_sha256": file_sha256(root / ANNOTATIONS_PATH),
    }
    if any(preparation.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("Prepared dataset checksum differs from its recorded identity")
    with (root / MANIFEST_PATH).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    expected_frames = {
        (item["sequence"], str(frame))
        for item in protocol["sequences"]
        for frame in item["frames"]
    }
    actual_frames = {(row["source_group_id"], row["frame_number"]) for row in rows}
    if len(rows) != len(expected_frames) or actual_frames != expected_frames:
        raise ValueError("Manifest does not match the frozen sequence/frame selection")
    hashes = set()
    for row in rows:
        sequence, frame = row["source_group_id"], int(row["frame_number"])
        image_path = DATA_DIRECTORY / "images" / sequence / f"img{frame:06d}.jpg"
        if (
            row["dataset_role"] != "validation"
            or row["source_split"] != "train"
            or row["dataset_version"] != PROTOCOL_VERSION
            or row["asset_id"] != f"uavdt_{sequence}_{frame:06d}"
            or row["evaluation_image_path"] != image_path.as_posix()
        ):
            raise ValueError("Manifest role, version or media identity mismatch")
        if row["image_sha256"] in hashes:
            raise ValueError("Exact duplicate image bytes in selected development data")
        hashes.add(row["image_sha256"])
    for item in protocol["sequences"]:
        sequence = item["sequence"]
        for relative, field in (
            (f"GT/{sequence}_gt_whole.txt", "detection_sha256"),
            (f"GT/{sequence}_gt_ignore.txt", "ignore_sha256"),
            (f"attributes/train/{sequence}_attr.txt", "attribute_sha256"),
        ):
            if file_sha256(root / DATA_DIRECTORY / relative) != item[field]:
                raise ValueError(f"Native source file checksum mismatch: {relative}")
    # Rebuild in memory: this also decodes and hashes every selected image.
    rebuilt = build_uavdt_annotations(
        repository_root=root,
        manifest_path=MANIFEST_PATH,
        gt_directory=DATA_DIRECTORY / "GT",
        attributes_directory=DATA_DIRECTORY / "attributes",
        role="validation",
        output_path=ANNOTATIONS_PATH,
    )
    canonical = json.loads((root / ANNOTATIONS_PATH).read_text(encoding="utf-8"))
    if canonical != rebuilt:
        raise ValueError("Canonical annotations differ from unmodified native labels")
    dataset = load_evaluation_dataset(root, config.dataset)
    if dataset.ignore_policy != UAVDT_IGNORE_POLICY:
        raise ValueError("Source-ignore policy is missing")
    model_path = config.resolve_path(root, config.model.weights_path)
    if file_sha256(model_path) != protocol["checkpoint_sha256"]:
        raise ValueError("Baseline checkpoint checksum mismatch")
    assets = dataset.asset_by_id()
    labels_inside_ignore = sum(
        any(
            region.asset_id == label.asset_id and region.contains(label.box)
            for region in dataset.ignored_regions
        )
        for label in dataset.ground_truth_boxes
    )
    out_of_bounds = sum(
        label.box.x < 0
        or label.box.y < 0
        or label.box.x + label.box.width > assets[label.asset_id].width
        or label.box.y + label.box.height > assets[label.asset_id].height
        for label in dataset.ground_truth_boxes
    )
    return {
        "status": "ready_for_source_label_development_baseline_only",
        **expected_hashes,
        "preparation_sha256": file_sha256(root / PREPARATION_PATH),
        "baseline_config_sha256": protocol["baseline_config_sha256"],
        "images": len(dataset.assets),
        "sequences": len(protocol["sequences"]),
        "box_counts": dict(
            Counter(b.project_class for b in dataset.ground_truth_boxes)
        ),
        "ignored_regions": len(dataset.ignored_regions),
        "labelled_boxes_inside_ignore": labels_inside_ignore,
        "out_of_bounds_boxes": out_of_bounds,
        "known_label_concerns": protocol["known_label_concerns"],
        "human_annotation_review": False,
        "final_holdout_authorized": False,
        "model_adoption_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    try:
        config = load_evaluation_config(args.repository_root / args.config)
        result = validate_uavdt_evaluation(args.repository_root, config)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"UAVDT baseline is not ready: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
