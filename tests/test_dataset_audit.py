import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from evaluation.dataset_audit import DATA, audit_dataset
from evaluation.dataset_selection import sha256


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def dataset(tmp_path):
    directory = tmp_path / DATA
    directory.mkdir(parents=True)
    rows = []
    for asset, role, kind, label in (
        ("traffic", "validation", "bounding_box", "car_or_van"),
        ("people", "held_out_test", "bounding_box", "person"),
        ("crowd", "held_out_test", "point_count", "person"),
    ):
        media = directory / f"{asset}.png"
        media.write_bytes(asset.encode())
        annotation = directory / (
            f"{asset}.json" if kind == "bounding_box" else "counts.csv"
        )
        rows.append(
            {
                "asset_id": asset,
                "dataset_version": "test-v1",
                "dataset_role": role,
                "collection_id": asset,
                "source_group_id": f"group_{asset}",
                "evaluation_image_path": media.relative_to(tmp_path).as_posix(),
                "width": "1000",
                "height": "1000",
                "annotation_type": kind,
                "target_classes": label,
                "canonical_annotation_path": annotation.relative_to(
                    tmp_path
                ).as_posix(),
                "image_sha256": sha256(media),
                "qc_status": "pending",
                "location": "shared broad location"
                if asset != "crowd"
                else "not_recorded",
                "source_url": "https://example.test/source",
                "license_id": "test-only",
                "license_url": "https://example.test/license",
            }
        )
        if kind == "bounding_box":
            sizes = (
                [(31, 31), (32, 32), (96, 96)]
                if asset == "traffic"
                else [(4, 4), (3, 5)]
            )
            annotations = [
                {
                    "id": i,
                    "image_id": 1,
                    "category_id": 1,
                    "bbox": [1, 1, w, h],
                    "source_attributes": {}
                    if asset == "traffic"
                    else {"occluded": i == 0},
                }
                for i, (w, h) in enumerate(sizes)
            ]
            annotation.write_text(
                json.dumps(
                    {
                        "images": [{"id": 1, "asset_id": asset}],
                        "categories": [{"id": 1, "name": label}],
                        "annotations": annotations,
                    }
                )
            )
        else:
            write_csv(
                annotation,
                [{"asset_id": asset, "dataset_role": role, "person_count": 42}],
            )
    write_csv(directory / "manifest.csv", rows)
    write_csv(
        directory / "qc_reviews.csv",
        [
            {
                "asset_id": row["asset_id"],
                "reviewer": "Test reviewer",
                "reviewed_on": "2026-09-01",
                "decision": "confirmed",
                "changes_made": "0",
                "notes": "fixture",
            }
            for row in rows
        ],
    )
    write_csv(
        directory / "exclusions.csv", [{"asset_id": "removed", "reason": "fixture"}]
    )
    return tmp_path


def test_audit_separates_boxes_points_sizes_and_recorded_reviews(dataset):
    report = audit_dataset(dataset, verify_media=True)
    summary = report["summary"]
    assert (
        summary["images"],
        summary["bounding_box_images"],
        summary["point_count_images"],
    ) == (3, 2, 1)
    assert summary["point_reference_people"] == 42
    assert summary["box_classes"]["person"]["boxes"] == 2
    assert summary["box_classes"]["person"]["declared_box_labelled_images"] == 1
    assert summary["box_classes"]["person"]["boxes_with_side_below_4px"] == 1
    assert summary["box_classes"]["car_or_van"]["size_counts"] == {
        "small": 1,
        "medium": 1,
        "large": 1,
    }
    assert summary["box_classes"]["bus"]["boxes"] == 0
    assert report["quality_control"]["manifest_review_status_disagreements"] == 3
    assert report["quality_control"]["recorded_reviewed_images"] == 3
    assert report["by_role"]["validation"]["box_classes"]["person"]["boxes"] == 0
    assert report["by_collection"]["crowd"]["point_reference_people"] == 42
    assert report["occlusion_by_collection"]["traffic"]["unknown"] == 3
    assert report["occlusion_by_collection"]["people"] == {
        "occluded": 1,
        "not_occluded": 1,
        "unknown": 0,
    }
    assert report["split_checks"]["source_groups_crossing_roles"] == {}
    assert report["split_checks"]["location_labels_crossing_roles"] == {
        "shared broad location": ["held_out_test", "validation"]
    }
    assert report["media_hashes_verified"] is True
    for path, checksum in report["input_sha256"].items():
        assert sha256(dataset / path) == checksum
    assert audit_dataset(dataset, verify_media=True) == report


@pytest.mark.parametrize(
    "change", ["missing", "excluded", "invalid_date", "no_reviewer"]
)
def test_incomplete_or_excluded_reviews_are_not_counted_as_accepted(dataset, change):
    path = dataset / DATA / "qc_reviews.csv"
    rows = list(csv.DictReader(path.open()))
    if change == "missing":
        rows.pop(0)
    elif change == "excluded":
        rows[0]["decision"] = "excluded"
    elif change == "invalid_date":
        rows[0]["reviewed_on"] = "not-a-date"
    else:
        rows[0]["reviewer"] = ""
    write_csv(path, rows)
    report = audit_dataset(dataset)
    assert report["quality_control"]["recorded_reviewed_images"] == 2
    assert (
        report["summary"]["box_classes"]["car_or_van"]["recorded_reviewed_boxes"] == 0
    )


def test_split_and_exact_duplicate_flags_do_not_silently_change_membership(dataset):
    path = dataset / DATA / "manifest.csv"
    rows = list(csv.DictReader(path.open()))
    rows[1]["source_group_id"] = rows[0]["source_group_id"]
    rows[1]["image_sha256"] = rows[0]["image_sha256"]
    write_csv(path, rows)
    report = audit_dataset(dataset)
    checks = report["split_checks"]
    assert checks["source_groups_crossing_roles"] == {
        "group_traffic": ["held_out_test", "validation"]
    }
    assert checks["duplicate_image_hash_groups"] == [["traffic", "people"]]
    assert report["summary"]["images"] == 3


def test_media_checksum_mismatch_fails(dataset):
    (dataset / DATA / "traffic.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Image checksum mismatch"):
        audit_dataset(dataset, verify_media=True)


@pytest.mark.parametrize("filename", ["manifest.csv", "qc_reviews.csv"])
def test_duplicate_asset_identity_is_rejected(dataset, filename):
    path = dataset / DATA / filename
    rows = list(csv.DictReader(path.open()))
    write_csv(path, [*rows, rows[0]])
    with pytest.raises(ValueError, match="Duplicate"):
        audit_dataset(dataset)


def test_nonfinite_box_cannot_inflate_size_counts(dataset):
    path = dataset / DATA / "traffic.json"
    data = json.loads(path.read_text())
    data["annotations"][0]["bbox"][2] = float("nan")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Invalid box geometry"):
        audit_dataset(dataset)


def test_out_of_scope_annotations_are_reported_not_counted_as_targets(dataset):
    path = dataset / DATA / "traffic.json"
    data = json.loads(path.read_text())
    data["categories"].append({"id": 2, "name": "person"})
    data["annotations"].append(
        {"id": 4, "image_id": 1, "category_id": 2, "bbox": [1, 1, 10, 10]}
    )
    path.write_text(json.dumps(data))
    report = audit_dataset(dataset)
    assert report["out_of_scope_box_annotations"] == {"traffic": {"person": 1}}
    assert report["summary"]["box_classes"]["person"]["boxes"] == 2
    assert report["occlusion_by_collection"]["traffic"]["unknown"] == 3


@pytest.mark.parametrize("filename", ["manifest.csv", "traffic.json", "traffic.png"])
def test_cli_rejects_overwriting_dataset_inputs(dataset, filename):
    output = dataset / DATA / filename
    before = output.read_bytes()
    result = run_cli(dataset, output)
    assert result.returncode == 2
    assert "must not overwrite an input file" in result.stderr
    assert output.read_bytes() == before


def run_cli(dataset, output):
    script = Path(__file__).resolve().parents[1] / "scripts/audit_evaluation_dataset.py"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--repository-root",
            str(dataset),
            "--output",
            str(output),
            "--verify-media",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_writes_a_reproducible_report(dataset):
    output = dataset / "reports/audit.json"
    result = run_cli(dataset, output)
    assert result.returncode == 0, result.stderr
    assert "Audited 3 images" in result.stdout
    assert json.loads(output.read_text()) == audit_dataset(dataset, verify_media=True)
