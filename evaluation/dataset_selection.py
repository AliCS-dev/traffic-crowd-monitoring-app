from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

DATASET_VERSION = "1.0-draft"
ALLOWED_ROLES = {"training", "validation", "held_out_test"}
COLLECTION_NAMES = {
    "traffic_uav": "Traffic Images Captured from UAVs",
    "okutama_action": "Okutama-Action",
    "dlr_acd": "DLR Aerial Crowd Dataset",
    "wikimedia": "Wikimedia Commons",
}
MANIFEST_FIELDS = [
    "asset_id",
    "dataset_version",
    "collection_id",
    "source_group_id",
    "source_split",
    "dataset_role",
    "source_name",
    "publisher",
    "creator",
    "source_url",
    "license_id",
    "license_url",
    "accessed_on",
    "original_filename",
    "source_media_path",
    "evaluation_image_path",
    "media_type",
    "frame_number",
    "timestamp_seconds",
    "width",
    "height",
    "scene_type",
    "location",
    "viewpoint",
    "lighting",
    "weather",
    "target_classes",
    "annotation_type",
    "annotation_source_path",
    "canonical_annotation_path",
    "image_sha256",
    "qc_status",
    "notes",
]
EXCLUSION_FIELDS = ["asset_id", "excluded_on", "decision_stage", "reason"]


def uniform_indices(total: int, count: int) -> list[int]:
    """Return deterministic midpoint samples spread across a sequence."""
    if total <= 0:
        raise ValueError("A source must contain at least one item")
    if count <= 0:
        raise ValueError("sample_count must be positive")
    if count > total:
        raise ValueError(f"Cannot select {count} items from a source of {total}")

    return [((2 * index + 1) * total) // (2 * count) for index in range(count)]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def validate_selection_plan(rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError("The selection plan is empty")

    selection_ids: set[str] = set()
    group_roles: dict[str, str] = {}

    for row in rows:
        selection_id = row["selection_id"]
        if not selection_id or selection_id in selection_ids:
            raise ValueError(f"Duplicate or empty selection_id: {selection_id!r}")
        selection_ids.add(selection_id)

        role = row["dataset_role"]
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Unknown dataset role for {selection_id}: {role}")

        source_group = row["source_group_id"]
        if not source_group:
            raise ValueError(f"Missing source group for {selection_id}")
        previous_role = group_roles.setdefault(source_group, role)
        if previous_role != role:
            raise ValueError(
                f"Source group {source_group} appears in {previous_role} and {role}"
            )

        try:
            sample_count = int(row["sample_count"])
        except ValueError as error:
            raise ValueError(
                f"Invalid sample_count for {selection_id}: {row['sample_count']}"
            ) from error
        if sample_count <= 0:
            raise ValueError(f"sample_count must be positive for {selection_id}")


def natural_sort_key(path: Path) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.name)
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path, repository_root: Path) -> str:
    return path.resolve().relative_to(repository_root.resolve()).as_posix()


def frame_number(path: Path, media_type: str) -> str:
    if media_type != "image_sequence":
        return ""
    match = re.search(r"(\d+)$", path.stem)
    if not match:
        raise ValueError(f"Cannot read frame number from {path}")
    return str(int(match.group(1)))


def annotation_path(
    row: dict[str, str], image_path: Path, repository_root: Path
) -> str:
    source = row["annotation_source"]
    if source == "manual":
        return ""

    source_path = repository_root / source
    if row["annotation_type"] == "point_count":
        annotation = source_path / f"{image_path.stem}.png"
    elif source_path.is_dir():
        annotation = source_path / f"{image_path.stem}.txt"
    else:
        annotation = source_path

    if not annotation.is_file():
        raise FileNotFoundError(f"Missing annotation source: {annotation}")
    return relative_path(annotation, repository_root)


def image_details(path: Path) -> tuple[int, int, str]:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Cannot read selected image: {path}")
    height, width = image.shape[:2]
    return width, height, sha256(path)


def select_image_paths(row: dict[str, str], repository_root: Path) -> list[Path]:
    source = repository_root / row["source_path"]
    if source.is_file():
        available = [source]
    else:
        available = sorted(source.glob(row["file_pattern"]), key=natural_sort_key)

    count = int(row["sample_count"])
    indices = uniform_indices(len(available), count)
    return [available[index] for index in indices]


def select_video_frames(
    row: dict[str, str], repository_root: Path, derived_root: Path
) -> list[tuple[Path, int, float]]:
    source = repository_root / row["source_path"]
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError(f"Cannot open selected video: {source}")

    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if total_frames <= 0 or fps <= 0:
        capture.release()
        raise ValueError(f"Invalid video metadata: {source}")

    output_directory = derived_root / "frames" / row["selection_id"]
    output_directory.mkdir(parents=True, exist_ok=True)
    selected: list[tuple[Path, int, float]] = []

    try:
        for index in uniform_indices(total_frames, int(row["sample_count"])):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"Cannot read frame {index} from {source}")

            output_path = output_directory / f"frame_{index:06d}.png"
            if not cv2.imwrite(str(output_path), frame):
                raise ValueError(f"Cannot write selected frame: {output_path}")
            selected.append((output_path, index, index / fps))
    finally:
        capture.release()

    return selected


def download_records(path: Path) -> dict[str, dict[str, str]]:
    records = read_csv_rows(path)
    return {record["download_id"]: record for record in records}


def exclusion_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()

    rows = read_csv_rows(path)
    excluded: set[str] = set()
    for row in rows:
        asset_id = row["asset_id"]
        if not asset_id or asset_id in excluded:
            raise ValueError(f"Duplicate or empty excluded asset_id: {asset_id!r}")
        if not all(row[field] for field in EXCLUSION_FIELDS[1:]):
            raise ValueError(f"Incomplete exclusion record for {asset_id}")
        excluded.add(asset_id)
    return excluded


def apply_exclusions(
    records: list[dict[str, Any]], excluded: set[str]
) -> list[dict[str, Any]]:
    generated_ids = {record["asset_id"] for record in records}
    unknown = sorted(excluded - generated_ids)
    if unknown:
        raise ValueError(f"Exclusion records reference unknown assets: {unknown}")
    return [record for record in records if record["asset_id"] not in excluded]


def base_manifest_record(
    row: dict[str, str], download: dict[str, str]
) -> dict[str, Any]:
    return {
        "dataset_version": DATASET_VERSION,
        "collection_id": row["collection_id"],
        "source_group_id": row["source_group_id"],
        "source_split": row["source_split"],
        "dataset_role": row["dataset_role"],
        "source_name": COLLECTION_NAMES[row["collection_id"]],
        "publisher": download["publisher"],
        "creator": download["creator"],
        "source_url": download["source_page_url"],
        "license_id": download["license_id"],
        "license_url": download["license_url"],
        "accessed_on": download["accessed_on"],
        "scene_type": row["scene_type"],
        "location": row["location"],
        "viewpoint": row["viewpoint"],
        "lighting": row["lighting"],
        "weather": row["weather"],
        "target_classes": row["target_classes"],
        "annotation_type": row["annotation_type"],
        "qc_status": "pending",
        "notes": row["notes"],
    }


def canonical_annotation_path(row: dict[str, str]) -> str:
    if row["annotation_type"] == "point_count":
        return "data/evaluation/derived/annotations/dlr_person_counts.csv"
    return f"data/evaluation/derived/annotations/instances_{row['dataset_role']}.json"


def image_manifest_record(
    row: dict[str, str],
    download: dict[str, str],
    image_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    number = frame_number(image_path, row["media_type"])
    suffix = f"_f{int(number):06d}" if number else f"_{image_path.stem.lower()}"
    width, height, image_hash = image_details(image_path)
    record = base_manifest_record(row, download)
    record.update(
        {
            "asset_id": f"{row['selection_id']}{suffix}",
            "original_filename": image_path.name,
            "source_media_path": relative_path(image_path, repository_root),
            "evaluation_image_path": relative_path(image_path, repository_root),
            "media_type": "image",
            "frame_number": number,
            "timestamp_seconds": "",
            "width": width,
            "height": height,
            "annotation_source_path": annotation_path(row, image_path, repository_root),
            "canonical_annotation_path": canonical_annotation_path(row),
            "image_sha256": image_hash,
        }
    )
    return record


def video_manifest_records(
    row: dict[str, str],
    download: dict[str, str],
    repository_root: Path,
    derived_root: Path,
) -> list[dict[str, Any]]:
    source_path = repository_root / row["source_path"]
    records = []
    for image_path, number, timestamp in select_video_frames(
        row, repository_root, derived_root
    ):
        width, height, image_hash = image_details(image_path)
        record = base_manifest_record(row, download)
        record.update(
            {
                "asset_id": f"{row['selection_id']}_f{number:06d}",
                "original_filename": source_path.name,
                "source_media_path": relative_path(source_path, repository_root),
                "evaluation_image_path": relative_path(image_path, repository_root),
                "media_type": "video_frame",
                "frame_number": number,
                "timestamp_seconds": f"{timestamp:.6f}",
                "width": width,
                "height": height,
                "annotation_source_path": "",
                "canonical_annotation_path": canonical_annotation_path(row),
                "image_sha256": image_hash,
            }
        )
        records.append(record)
    return records


def build_manifest(
    repository_root: Path,
    plan_path: Path,
    downloads_path: Path,
    manifest_path: Path,
    derived_root: Path,
    exclusions_path: Path | None = None,
) -> list[dict[str, Any]]:
    plan = read_csv_rows(plan_path)
    validate_selection_plan(plan)
    downloads = download_records(downloads_path)
    records: list[dict[str, Any]] = []

    for row in plan:
        try:
            download = downloads[row["download_id"]]
        except KeyError as error:
            raise ValueError(
                f"Unknown download_id for {row['selection_id']}: {row['download_id']}"
            ) from error

        if row["media_type"] == "video":
            records.extend(
                video_manifest_records(row, download, repository_root, derived_root)
            )
        else:
            records.extend(
                image_manifest_record(row, download, image_path, repository_root)
                for image_path in select_image_paths(row, repository_root)
            )

    records = apply_exclusions(
        records, exclusion_ids(exclusions_path) if exclusions_path else set()
    )
    asset_ids = [record["asset_id"] for record in records]
    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("Generated manifest contains duplicate asset identifiers")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=MANIFEST_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(records)

    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select aerial evaluation assets and build their manifest."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.repository_root.resolve()
    records = build_manifest(
        repository_root=root,
        plan_path=root / "data/evaluation/selection_plan.csv",
        downloads_path=root / "data/evaluation/downloads.csv",
        manifest_path=root / "data/evaluation/manifest.csv",
        derived_root=root / "data/evaluation/derived",
        exclusions_path=root / "data/evaluation/exclusions.csv",
    )

    role_counts = Counter(record["dataset_role"] for record in records)
    collection_counts = Counter(record["collection_id"] for record in records)
    print(f"Selected {len(records)} evaluation assets")
    print(
        "Roles: "
        + ", ".join(f"{key}={value}" for key, value in sorted(role_counts.items()))
    )
    print(
        "Collections: "
        + ", ".join(
            f"{key}={value}" for key, value in sorted(collection_counts.items())
        )
    )


if __name__ == "__main__":
    main()
