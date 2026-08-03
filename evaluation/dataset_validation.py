from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2

from evaluation.annotation_conversion import PROJECT_CATEGORIES
from evaluation.dataset_selection import ALLOWED_ROLES, MANIFEST_FIELDS, sha256

REQUIRED_VALUES = {
    "asset_id",
    "dataset_version",
    "collection_id",
    "source_group_id",
    "source_split",
    "dataset_role",
    "source_url",
    "license_id",
    "license_url",
    "evaluation_image_path",
    "width",
    "height",
    "target_classes",
    "annotation_type",
    "canonical_annotation_path",
    "image_sha256",
    "qc_status",
}
QC_DECISIONS = {"confirmed", "corrected", "excluded"}
CATEGORY_NAMES = {category["id"]: category["name"] for category in PROJECT_CATEGORIES}


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)

    @property
    def technically_valid(self) -> bool:
        return not self.errors

    @property
    def dataset_ready(self) -> bool:
        return not self.errors and not self.incomplete

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["technically_valid"] = self.technically_valid
        result["dataset_ready"] = self.dataset_ready
        return result


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return reader.fieldnames or [], list(reader)


def duplicates(values: list[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def validate_manifest(
    repository_root: Path,
    manifest_path: Path,
    report: ValidationReport,
    verify_hashes: bool,
) -> list[dict[str, str]]:
    fields, records = read_csv(manifest_path)
    missing_fields = set(MANIFEST_FIELDS) - set(fields)
    if missing_fields:
        report.errors.append(
            "Manifest fields are missing: " + ", ".join(sorted(missing_fields))
        )
        return records

    duplicate_ids = duplicates([record["asset_id"] for record in records])
    if duplicate_ids:
        report.errors.append("Duplicate asset IDs: " + ", ".join(sorted(duplicate_ids)))

    duplicate_hashes = duplicates([record["image_sha256"] for record in records])
    if duplicate_hashes:
        report.errors.append(
            f"The manifest contains {len(duplicate_hashes)} duplicate image hashes"
        )

    group_roles: dict[str, set[str]] = defaultdict(set)
    role_counts: Counter[str] = Counter()
    collection_counts: Counter[str] = Counter()

    for record in records:
        asset_id = record["asset_id"] or "<empty>"
        missing_values = [field for field in REQUIRED_VALUES if not record[field]]
        if missing_values:
            report.errors.append(
                f"{asset_id} is missing: {', '.join(sorted(missing_values))}"
            )
            continue

        role = record["dataset_role"]
        if role not in ALLOWED_ROLES:
            report.errors.append(f"{asset_id} has unknown role: {role}")
        group_roles[record["source_group_id"]].add(role)
        role_counts[role] += 1
        collection_counts[record["collection_id"]] += 1

        image_path = repository_root / record["evaluation_image_path"]
        image = cv2.imread(str(image_path))
        if image is None:
            report.errors.append(f"Missing or unreadable image: {image_path}")
            continue
        actual_height, actual_width = image.shape[:2]
        if (actual_width, actual_height) != (
            int(record["width"]),
            int(record["height"]),
        ):
            report.errors.append(f"Image dimensions do not match: {asset_id}")
        if verify_hashes and sha256(image_path) != record["image_sha256"]:
            report.errors.append(f"Image SHA-256 does not match: {asset_id}")

    overlapping_groups = {
        group: roles for group, roles in group_roles.items() if len(roles) > 1
    }
    if overlapping_groups:
        report.errors.append(
            f"{len(overlapping_groups)} source groups cross dataset roles"
        )

    report.statistics["manifest"] = {
        "assets": len(records),
        "source_groups": len(group_roles),
        "roles": dict(sorted(role_counts.items())),
        "collections": dict(sorted(collection_counts.items())),
    }
    return records


def validate_coco_file(
    path: Path,
    expected_records: list[dict[str, str]],
    report: ValidationReport,
) -> None:
    if not path.is_file():
        report.errors.append(f"Missing COCO annotation file: {path}")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    category_ids = {category["id"] for category in data.get("categories", [])}
    if category_ids != set(CATEGORY_NAMES):
        report.errors.append(f"Unexpected category definitions in {path}")

    images = data.get("images", [])
    annotations = data.get("annotations", [])
    image_ids = {image["id"] for image in images}
    asset_ids = {image.get("asset_id") for image in images}
    expected_ids = {record["asset_id"] for record in expected_records}
    if asset_ids != expected_ids:
        report.errors.append(f"COCO image membership does not match manifest: {path}")

    if len(image_ids) != len(images):
        report.errors.append(f"Duplicate COCO image IDs: {path}")
    annotation_ids = [annotation["id"] for annotation in annotations]
    if len(annotation_ids) != len(set(annotation_ids)):
        report.errors.append(f"Duplicate COCO annotation IDs: {path}")

    image_lookup = {image["id"]: image for image in images}
    class_counts: Counter[str] = Counter()
    size_counts: Counter[str] = Counter()
    labelled_images: set[int] = set()

    for annotation in annotations:
        annotation_id = annotation.get("id", "<unknown>")
        image_id = annotation.get("image_id")
        category_id = annotation.get("category_id")
        if image_id not in image_ids:
            report.errors.append(
                f"Annotation {annotation_id} references an unknown image in {path}"
            )
            continue
        if category_id not in CATEGORY_NAMES:
            report.errors.append(
                f"Annotation {annotation_id} has an unknown category in {path}"
            )
            continue

        bbox = annotation.get("bbox", [])
        if len(bbox) != 4:
            report.errors.append(f"Annotation {annotation_id} has a malformed box")
            continue
        x, y, width, height = bbox
        image = image_lookup[image_id]
        if (
            x < 0
            or y < 0
            or width <= 0
            or height <= 0
            or x + width > image["width"] + 1e-6
            or y + height > image["height"] + 1e-6
        ):
            report.errors.append(
                f"Annotation {annotation_id} is outside its image in {path}"
            )
        expected_area = width * height
        if abs(annotation.get("area", -1) - expected_area) > 1e-3:
            report.errors.append(f"Annotation {annotation_id} has an invalid area")

        class_counts[CATEGORY_NAMES[category_id]] += 1
        if expected_area < 32 * 32:
            size_counts["small"] += 1
        elif expected_area < 96 * 96:
            size_counts["medium"] += 1
        else:
            size_counts["large"] += 1
        labelled_images.add(image_id)

    role = expected_records[0]["dataset_role"] if expected_records else path.stem
    report.statistics.setdefault("bounding_boxes", {})[role] = {
        "images": len(images),
        "boxes": len(annotations),
        "empty_images": len(images) - len(labelled_images),
        "classes": dict(sorted(class_counts.items())),
        "object_sizes": dict(sorted(size_counts.items())),
    }


def validate_coco_annotations(
    repository_root: Path,
    records: list[dict[str, str]],
    report: ValidationReport,
) -> None:
    for role in sorted(ALLOWED_ROLES):
        expected = [
            record
            for record in records
            if record["dataset_role"] == role
            and record["annotation_type"] == "bounding_box"
            and record["canonical_annotation_path"]
        ]
        paths = {record["canonical_annotation_path"] for record in expected}
        if len(paths) != 1:
            report.errors.append(
                f"Expected one COCO annotation path for {role}; found {len(paths)}"
            )
            continue
        validate_coco_file(repository_root / paths.pop(), expected, report)


def validate_count_references(
    repository_root: Path,
    records: list[dict[str, str]],
    report: ValidationReport,
) -> None:
    expected = {
        record["asset_id"]: record
        for record in records
        if record["annotation_type"] == "point_count"
    }
    if not expected:
        return

    paths = {record["canonical_annotation_path"] for record in expected.values()}
    if len(paths) != 1:
        report.errors.append("Expected one DLR count-reference path")
        return
    path = repository_root / paths.pop()
    if not path.is_file():
        report.errors.append(f"Missing DLR count-reference file: {path}")
        return

    _, rows = read_csv(path)
    actual_ids = {row["asset_id"] for row in rows}
    if actual_ids != set(expected):
        report.errors.append("DLR count-reference membership does not match manifest")

    role_counts: Counter[str] = Counter()
    role_people: Counter[str] = Counter()
    for row in rows:
        try:
            person_count = int(row["person_count"])
        except ValueError:
            report.errors.append(f"Invalid DLR person count: {row['asset_id']}")
            continue
        if person_count < 0:
            report.errors.append(f"Negative DLR person count: {row['asset_id']}")
        role_counts[row["dataset_role"]] += 1
        role_people[row["dataset_role"]] += person_count

    report.statistics["point_counts"] = {
        role: {"images": role_counts[role], "people": role_people[role]}
        for role in sorted(role_counts)
    }


def validate_qc_reviews(
    qc_path: Path, records: list[dict[str, str]], report: ValidationReport
) -> None:
    fields, reviews = read_csv(qc_path)
    expected_fields = {
        "asset_id",
        "reviewer",
        "reviewed_on",
        "decision",
        "changes_made",
        "notes",
    }
    if set(fields) != expected_fields:
        report.errors.append("Quality-control review fields are invalid")
        return

    review_ids = [review["asset_id"] for review in reviews]
    duplicate_ids = duplicates(review_ids)
    if duplicate_ids:
        report.errors.append("Quality-control records contain duplicate asset IDs")

    manifest_ids = {record["asset_id"] for record in records}
    unknown_ids = set(review_ids) - manifest_ids
    if unknown_ids:
        report.errors.append("Quality-control records contain unknown asset IDs")

    valid_reviews = {
        review["asset_id"]
        for review in reviews
        if review["reviewer"]
        and review["reviewed_on"]
        and review["decision"] in QC_DECISIONS
    }
    missing_reviews = manifest_ids - valid_reviews
    if missing_reviews:
        report.incomplete.append(
            f"{len(missing_reviews)} images still require a recorded QC decision"
        )
    report.statistics["quality_control"] = {
        "recorded": len(valid_reviews),
        "required": len(records),
        "decisions": dict(
            sorted(
                Counter(
                    review["decision"] for review in reviews if review["decision"]
                ).items()
            )
        ),
    }


def validate_dataset(
    repository_root: Path, verify_hashes: bool = True
) -> ValidationReport:
    report = ValidationReport()
    records = validate_manifest(
        repository_root,
        repository_root / "data/evaluation/manifest.csv",
        report,
        verify_hashes,
    )
    validate_coco_annotations(repository_root, records, report)
    validate_count_references(repository_root, records, report)
    validate_qc_reviews(
        repository_root / "data/evaluation/qc_reviews.csv", records, report
    )
    return report


def write_report(path: Path, report: ValidationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def print_report(report: ValidationReport) -> None:
    print(f"Technical validation: {'PASS' if report.technically_valid else 'FAIL'}")
    print(f"Dataset ready: {'YES' if report.dataset_ready else 'NO'}")
    for heading, messages in (
        ("Errors", report.errors),
        ("Incomplete work", report.incomplete),
        ("Warnings", report.warnings),
    ):
        if messages:
            print(f"{heading}:")
            for message in messages:
                print(f"- {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the evaluation dataset.")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Return success when technical checks pass but review work remains.",
    )
    parser.add_argument(
        "--skip-file-hashes",
        action="store_true",
        help="Skip image SHA-256 verification for a faster local check.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.repository_root.resolve()
    report = validate_dataset(root, verify_hashes=not args.skip_file_hashes)
    write_report(
        root / "data/evaluation/derived/reports/dataset_validation.json", report
    )
    print_report(report)
    if report.errors or (report.incomplete and not args.allow_incomplete):
        sys.exit(1)


if __name__ == "__main__":
    main()
