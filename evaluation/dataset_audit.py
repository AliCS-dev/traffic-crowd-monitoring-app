"""Describe existing annotation coverage without inference or split changes."""

import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from evaluation.dataset_selection import sha256
from evaluation.dataset_validation import read_csv
from evaluation.evaluation_config import PROJECT_CLASSES, DatasetSettings
from evaluation.evaluation_data import load_evaluation_dataset, parse_target_classes

DATA = Path("data/evaluation")
UNKNOWN = {"", "unknown", "not_recorded"}


def _reviewed(review):
    if not review or review["decision"] not in {"confirmed", "corrected"}:
        return False
    try:
        date.fromisoformat(review["reviewed_on"])
    except ValueError:
        return False
    return bool(review["reviewer"].strip())


def _class_support(rows, boxes, reviewed_ids):
    result = {}
    lookup = {row["asset_id"]: row for row in rows}
    for label in PROJECT_CLASSES:
        selected = [box for box in boxes if box.project_class == label]
        asset_ids = {box.asset_id for box in selected}
        sizes = Counter()
        tiny = 0
        for item in selected:
            width, height = item.box.width, item.box.height
            area = width * height
            sizes[
                "small" if area < 32**2 else "medium" if area < 96**2 else "large"
            ] += 1
            tiny += min(width, height) < 4
        result[label] = {
            "boxes": len(selected),
            "recorded_reviewed_boxes": sum(
                item.asset_id in reviewed_ids for item in selected
            ),
            "images_with_boxes": len(asset_ids),
            "source_groups_with_boxes": len(
                {lookup[asset_id]["source_group_id"] for asset_id in asset_ids}
            ),
            "declared_box_labelled_images": sum(
                row["annotation_type"] == "bounding_box"
                and label in parse_target_classes(row["target_classes"])
                for row in rows
            ),
            "size_counts": {name: sizes[name] for name in ("small", "medium", "large")},
            "boxes_with_side_below_4px": tiny,
        }
    return result


def _summary(rows, boxes, counts, reviewed_ids):
    return {
        "images": len(rows),
        "source_groups": len({row["source_group_id"] for row in rows}),
        "bounding_box_images": sum(
            row["annotation_type"] == "bounding_box" for row in rows
        ),
        "point_count_images": sum(
            row["annotation_type"] == "point_count" for row in rows
        ),
        "point_reference_people": sum(item.count for item in counts),
        "box_classes": _class_support(rows, boxes, reviewed_ids),
        "conditions": {
            field: dict(
                sorted(Counter(row.get(field, "") or "unknown" for row in rows).items())
            )
            for field in ("scene_type", "viewpoint", "lighting", "weather", "location")
        },
    }


def audit_dataset(root: Path, *, verify_media: bool = False) -> dict:
    manifest_path = DATA / "manifest.csv"
    reviews_path = DATA / "qc_reviews.csv"
    exclusions_path = DATA / "exclusions.csv"
    _, rows = read_csv(root / manifest_path)
    _, reviews = read_csv(root / reviews_path)
    _, exclusions = read_csv(root / exclusions_path)
    if not rows:
        raise ValueError("The audit requires a non-empty manifest.")
    for name, records in (("manifest", rows), ("review", reviews)):
        ids = [row["asset_id"] for row in records]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate {name} asset IDs.")
    versions = {row["dataset_version"] for row in rows}
    if len(versions) != 1:
        raise ValueError("The audit requires a single dataset version.")
    version = next(iter(versions))
    review_by_id = {review["asset_id"]: review for review in reviews}
    reviewed_ids = {
        row["asset_id"] for row in rows if _reviewed(review_by_id.get(row["asset_id"]))
    }
    boxes, counts = [], []
    for role in sorted({row["dataset_role"] for row in rows}):
        dataset = load_evaluation_dataset(
            root,
            DatasetSettings(version=version, role=role, manifest_path=manifest_path),
        )
        boxes.extend(dataset.ground_truth_boxes)
        counts.extend(dataset.count_references)
    lookup = {row["asset_id"]: row for row in rows}
    for item in boxes:
        values = item.box.as_xyxy()
        row = lookup[item.asset_id]
        if (
            not all(math.isfinite(value) for value in values)
            or min(values) < 0
            or values[2] > int(row["width"]) + 1e-6
            or values[3] > int(row["height"]) + 1e-6
        ):
            raise ValueError(f"Invalid box geometry for {item.asset_id}.")

    inputs = {manifest_path, reviews_path, exclusions_path}
    inputs.update(Path(row["canonical_annotation_path"]) for row in rows)
    input_hashes = {path.as_posix(): sha256(root / path) for path in sorted(inputs)}
    occlusion = defaultdict(Counter)
    out_of_scope = defaultdict(Counter)
    for path in sorted(
        {
            row["canonical_annotation_path"]
            for row in rows
            if row["annotation_type"] == "bounding_box"
        }
    ):
        data = json.loads((root / path).read_text(encoding="utf-8"))
        image_ids = {image["id"]: image["asset_id"] for image in data["images"]}
        categories = {
            category["id"]: category["name"] for category in data["categories"]
        }
        for annotation in data["annotations"]:
            row = lookup[image_ids[annotation["image_id"]]]
            label = categories[annotation["category_id"]]
            if label not in parse_target_classes(row["target_classes"]):
                out_of_scope[row["collection_id"]][label] += 1
                continue
            value = annotation.get("source_attributes", {}).get("occluded")
            state = (
                "occluded"
                if value is True
                else "not_occluded"
                if value is False
                else "unknown"
            )
            occlusion[row["collection_id"]][state] += 1

    group_roles, location_roles, hashes = (
        defaultdict(set),
        defaultdict(set),
        defaultdict(list),
    )
    for row in rows:
        group_roles[row["source_group_id"]].add(row["dataset_role"])
        if row.get("location", "") not in UNKNOWN:
            location_roles[row["location"]].add(row["dataset_role"])
        if row.get("image_sha256"):
            hashes[row["image_sha256"]].append(row["asset_id"])
        if verify_media:
            path = Path(row["evaluation_image_path"])
            if sha256(root / path) != row["image_sha256"]:
                raise ValueError(f"Image checksum mismatch: {row['asset_id']}")

    result = {
        "schema_version": 1,
        "purpose": (
            "Historical annotation coverage audit; not inference or a new holdout"
        ),
        "dataset_version": version,
        "input_sha256": input_hashes,
        "media_hashes_verified": verify_media,
        "out_of_scope_box_annotations": {
            collection: dict(sorted(values.items()))
            for collection, values in sorted(out_of_scope.items())
        },
        "summary": _summary(rows, boxes, counts, reviewed_ids),
        "quality_control": {
            "recorded_reviewed_images": len(reviewed_ids),
            "without_accepted_review_record": sorted(set(lookup) - reviewed_ids),
            "manifest_status_counts": dict(
                sorted(Counter(row["qc_status"] for row in rows).items())
            ),
            "manifest_review_status_disagreements": sum(
                row["asset_id"] in reviewed_ids
                and row["qc_status"] != review_by_id[row["asset_id"]]["decision"]
                for row in rows
            ),
            "reviewers": dict(
                sorted(Counter(review["reviewer"] for review in reviews).items())
            ),
            "recorded_decisions": dict(
                sorted(Counter(review["decision"] for review in reviews).items())
            ),
            "unknown_review_asset_ids": sorted(set(review_by_id) - set(lookup)),
            "excluded_asset_ids": sorted(row["asset_id"] for row in exclusions),
            "excluded_assets_still_selected": sorted(
                {row["asset_id"] for row in exclusions} & set(lookup)
            ),
        },
        "occlusion_by_collection": {
            collection: {
                state: values[state]
                for state in ("occluded", "not_occluded", "unknown")
            }
            for collection, values in sorted(occlusion.items())
        },
        "split_checks": {
            "source_groups_crossing_roles": {
                group: sorted(roles)
                for group, roles in sorted(group_roles.items())
                if len(roles) > 1
            },
            "duplicate_image_hash_groups": [
                ids for _, ids in sorted(hashes.items()) if len(ids) > 1
            ],
            "location_labels_crossing_roles": {
                location: sorted(roles)
                for location, roles in sorted(location_roles.items())
                if len(roles) > 1
            },
            "missing_image_hashes": sum(not row.get("image_sha256") for row in rows),
            "location_unknown_images": sum(
                row.get("location", "") in UNKNOWN for row in rows
            ),
            "near_duplicate_images": "not assessed by this audit",
            "source_group_independence": (
                "recorded grouping, not proof of independent locations or flights"
            ),
        },
        "missing_source_metadata": {
            field: sum(row.get(field, "") in UNKNOWN for row in rows)
            for field in ("source_url", "license_id", "license_url")
        },
    }
    for field, key in (("dataset_role", "by_role"), ("collection_id", "by_collection")):
        result[key] = {}
        for value in sorted({row[field] for row in rows}):
            selected = [row for row in rows if row[field] == value]
            ids = {row["asset_id"] for row in selected}
            result[key][value] = _summary(
                selected,
                [box for box in boxes if box.asset_id in ids],
                [item for item in counts if item.asset_id in ids],
                reviewed_ids,
            )
    result["source_groups"] = [
        {
            "source_group_id": group,
            "roles": sorted(roles),
            "images": sum(row["source_group_id"] == group for row in rows),
        }
        for group, roles in sorted(group_roles.items())
    ]
    return result
