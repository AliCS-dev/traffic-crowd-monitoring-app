import csv
import io
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np
import pytest

from evaluation import uavdt_preparation as preparation
from evaluation import uavdt_readiness as readiness
from evaluation.evaluation_config import load_evaluation_config

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def zip_bytes(members):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


@pytest.fixture
def source(tmp_path, monkeypatch, request):
    config_path = tmp_path / readiness.CONFIG_PATH
    config_path.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / readiness.CONFIG_PATH, config_path)
    config = load_evaluation_config(config_path)
    model = tmp_path / config.model.weights_path
    model.parent.mkdir(parents=True)
    model.write_bytes(b"synthetic checkpoint; not a model")
    monkeypatch.setattr(readiness, "CHECKPOINT_SHA256", readiness.file_sha256(model))
    attributes, annotations, images, sequences = {}, {}, {}, []
    for index in range(1, 30):
        sequence = f"M{index:04d}"
        split = "train" if index <= 17 else "test"
        member = f"M_attr/{split}/{sequence}_attr.txt"
        attrs = b"1,0,0,0,1,0,1,1,0,0\n"
        attributes[member] = attrs
        warning_case = getattr(request, "param", None) == "warnings" and index == 1
        boxes = "".join(
            f"{frame},{category},{-1 if warning_case and frame == 1 else 1},"
            f"1,2,2,1,{category},{category}\n"
            for frame in range(1, 11)
            for category in (1, 2, 3)
        ).encode()
        ignores = (
            b"1,4,-2,0,6,4,1,-1,-1\n" if warning_case else b"1,4,6,6,1,1,1,-1,-1\n"
        )
        for suffix, payload in (("whole", boxes), ("ignore", ignores)):
            annotations[f"UAV-benchmark-MOTD_v1.0/GT/{sequence}_gt_{suffix}.txt"] = (
                payload
            )
        sequences.append(
            {
                "sequence": sequence,
                "source_split": split,
                "daylight_only": True,
                "frame_min": 1,
                "frame_max": 10,
                "annotated_frames": 10,
                "attribute_member": member,
                "attribute_sha256": preparation.sha256(attrs),
                "detection_sha256": preparation.sha256(boxes),
                "ignore_sha256": preparation.sha256(ignores),
            }
        )
        # No test media exists, even in this synthetic archive.
        if split == "train":
            for frame in range(1, 11):
                image = np.full((8, 8, 3), index * 10 + frame, dtype=np.uint8)
                success, encoded = cv2.imencode(".jpg", image)
                assert success
                images[f"UAV-benchmark-M/{sequence}/img{frame:06d}.jpg"] = (
                    encoded.tobytes()
                )
    attrs = zip_bytes(attributes)
    attrs_path = (
        tmp_path / "data/evaluation/raw/source_inspection_20261007/uavdt/M_attr.zip"
    )
    attrs_path.parent.mkdir(parents=True)
    attrs_path.write_bytes(attrs)
    evidence = {
        "uavdt": {
            "attribute_zip_sha256": preparation.sha256(attrs),
            "sequences": sequences,
        }
    }
    write_json(tmp_path / readiness.EVIDENCE_PATH, evidence)
    monkeypatch.setattr(
        readiness,
        "EVIDENCE_SHA256",
        readiness.file_sha256(tmp_path / readiness.EVIDENCE_PATH),
    )
    write_json(tmp_path / readiness.PROTOCOL_PATH, readiness.build_protocol(tmp_path))

    class Archive(io.BytesIO):
        def __init__(self, url, size, *, byte_budget):
            payload = zip_bytes(annotations if "MOTD" in url else images)
            super().__init__(payload)
            self.url = url
            self.byte_budget = byte_budget
            self.downloaded_bytes = len(payload)
            self.requests = []

    monkeypatch.setattr(preparation, "HTTPRangeReader", Archive)
    return config


@pytest.fixture
def prepared(tmp_path, source):
    report = preparation.prepare_development_data(tmp_path, progress=lambda _: None)
    write_json(tmp_path / readiness.PREPARATION_PATH, report)
    return source


def refresh_receipt(root):
    path = root / readiness.PREPARATION_PATH
    record = json.loads(path.read_text())
    record["manifest_sha256"] = readiness.file_sha256(root / readiness.MANIFEST_PATH)
    record["canonical_sha256"] = readiness.file_sha256(
        root / readiness.ANNOTATIONS_PATH
    )
    write_json(path, record)


def modify_manifest(root, change):
    path = root / readiness.MANIFEST_PATH
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    change(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    refresh_receipt(root)


def test_actual_protocol_is_reproducible_and_reserves_test_sequences():
    protocol = readiness.load_protocol(ROOT)
    assert len(protocol["sequences"]) == 17
    assert sum(len(item["frames"]) for item in protocol["sequences"]) == 170
    assert len(protocol["reserved_test_sequences"]) == 12
    assert not (
        {item["sequence"] for item in protocol["sequences"]}
        & set(protocol["reserved_test_sequences"])
    )
    toll = next(item for item in protocol["sequences"] if item["sequence"] == "M0210")
    assert 583 in toll["frames"]
    assert protocol["human_annotation_review"] is False
    assert protocol["final_holdout_authorized"] is False


def test_sampling_has_exact_count_unique_frames_and_endpoints():
    assert readiness.evenly_spaced_frames(583) == [
        1,
        65,
        130,
        195,
        259,
        324,
        389,
        453,
        518,
        583,
    ]
    assert readiness.evenly_spaced_frames(10) == list(range(1, 11))
    with pytest.raises(ValueError):
        readiness.evenly_spaced_frames(9)


def test_complete_preparation_and_readiness_without_test_media(tmp_path, prepared):
    result = readiness.validate_uavdt_evaluation(tmp_path, prepared)
    assert result["images"] == 170
    assert result["sequences"] == 17
    assert result["box_counts"] == {"car_or_van": 170, "bus": 170, "truck": 170}
    assert result["ignored_regions"] == 17
    assert result["labelled_boxes_inside_ignore"] == 0
    assert result["out_of_bounds_boxes"] == 0
    assert result["model_adoption_authorized"] is False
    assert not (tmp_path / readiness.DATA_DIRECTORY / "attributes/test").exists()
    before = readiness.file_sha256(tmp_path / readiness.ANNOTATIONS_PATH)
    readiness.validate_uavdt_evaluation(tmp_path, prepared)
    assert readiness.file_sha256(tmp_path / readiness.ANNOTATIONS_PATH) == before
    with pytest.raises(FileExistsError):
        preparation.prepare_development_data(tmp_path)


@pytest.mark.parametrize("source", ["warnings"], indirect=True)
def test_native_label_warnings_are_retained_and_reported(tmp_path, prepared):
    result = readiness.validate_uavdt_evaluation(tmp_path, prepared)
    assert result["labelled_boxes_inside_ignore"] == 3
    assert result["out_of_bounds_boxes"] == 3
    assert sum(result["box_counts"].values()) == 510
    report = json.loads((tmp_path / readiness.PREPARATION_PATH).read_text())
    assert len(report["ground_truth_strictly_inside_ignore"]) == 3
    assert len(report["out_of_bounds_boxes"]) == 3


def test_changed_protocol_is_rejected_before_acquisition(tmp_path, source):
    path = tmp_path / readiness.PROTOCOL_PATH
    protocol = json.loads(path.read_text())
    protocol["sequences"][0]["source_split"] = "test"
    write_json(path, protocol)
    with pytest.raises(ValueError, match="protocol/configuration"):
        preparation.prepare_development_data(tmp_path)
    assert not (tmp_path / readiness.DATA_DIRECTORY).exists()


@pytest.mark.parametrize(
    "failure", ["source_hash", "unreadable_image", "duplicate_image"]
)
def test_incomplete_acquisition_never_produces_a_readiness_record(
    tmp_path, source, monkeypatch, failure
):
    read_member = preparation.read_member
    first_image = None

    def broken_member(archive, name, limit=2_000_000):
        nonlocal first_image
        payload = read_member(archive, name, limit)
        if failure == "source_hash" and name.endswith("_gt_whole.txt"):
            return payload + b"\n"
        if name.endswith(".jpg"):
            if failure == "unreadable_image":
                return b"not an image"
            if failure == "duplicate_image":
                first_image = first_image or payload
                return first_image
        return payload

    monkeypatch.setattr(preparation, "read_member", broken_member)
    with pytest.raises(ValueError, match="checksum|Unreadable|duplicate"):
        preparation.prepare_development_data(tmp_path, progress=lambda _: None)
    assert not (tmp_path / readiness.MANIFEST_PATH).exists()
    assert not (tmp_path / readiness.ANNOTATIONS_PATH).exists()
    assert not (tmp_path / readiness.DATA_DIRECTORY / "preparation.json").exists()


def test_changed_inventory_and_baseline_file_invalidate_protocol(tmp_path, source):
    config_path = tmp_path / readiness.CONFIG_PATH
    original = config_path.read_text()
    config_path.write_text(original + "\n")
    with pytest.raises(ValueError, match="protocol/configuration"):
        readiness.load_protocol(tmp_path)
    config_path.write_text(original)
    evidence = tmp_path / readiness.EVIDENCE_PATH
    evidence.write_text(evidence.read_text() + "\n")
    with pytest.raises(ValueError, match="inventory checksum"):
        readiness.load_protocol(tmp_path)


@pytest.mark.parametrize("corrupt_cache", [False, True])
def test_interrupted_download_can_resume_only_with_verified_cached_images(
    tmp_path, source, monkeypatch, corrupt_cache
):
    original_reader = preparation.read_member
    downloaded = []

    def interrupt(archive, name, limit=2_000_000):
        if name.endswith(".jpg"):
            if len(downloaded) == 3:
                raise ValueError("network interrupted")
            downloaded.append(name)
        return original_reader(archive, name, limit)

    monkeypatch.setattr(preparation, "read_member", interrupt)
    with pytest.raises(ValueError, match="network interrupted"):
        preparation.prepare_development_data(tmp_path, progress=lambda _: None)
    output = tmp_path / readiness.DATA_DIRECTORY
    assert (output / "download_attempt_001.json").exists()
    assert not (output / "preparation.json").exists()
    first = output / "images/M0001/img000001.jpg"
    if corrupt_cache:
        first.write_bytes(b"corrupt cache")

    def resume_reader(archive, name, limit=2_000_000):
        assert name not in downloaded, "Cached images must not be fetched again"
        return original_reader(archive, name, limit)

    monkeypatch.setattr(preparation, "read_member", resume_reader)
    if corrupt_cache:
        with pytest.raises(ValueError, match="Cached image differs"):
            preparation.prepare_development_data(
                tmp_path, resume=True, progress=lambda _: None
            )
        assert first.read_bytes() == b"corrupt cache"
        assert not (output / "preparation.json").exists()
    else:
        report = preparation.prepare_development_data(
            tmp_path, resume=True, progress=lambda _: None
        )
        assert report["cached_images_at_attempt_start"] == 3
        assert report["images"] == 170
        write_json(tmp_path / readiness.PREPARATION_PATH, report)
        assert readiness.validate_uavdt_evaluation(tmp_path, source)["images"] == 170
        with pytest.raises(ValueError, match="already converted"):
            preparation.prepare_development_data(tmp_path, resume=True)
    assert (output / "download_attempt_002.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        lambda config: replace(config, protocol_version="1.0"),
        lambda config: replace(
            config, dataset=replace(config.dataset, role="held_out_test")
        ),
        lambda config: replace(
            config, inference=replace(config.inference, operating_confidence=0.5)
        ),
        lambda config: replace(config, random_seed=7),
    ],
)
def test_only_frozen_baseline_configuration_is_allowed(tmp_path, prepared, change):
    with pytest.raises(ValueError, match="baseline is authorized"):
        readiness.validate_uavdt_evaluation(tmp_path, change(prepared))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("dataset_role", "held_out_test", "role, version"),
        ("source_split", "test", "role, version"),
        ("dataset_version", "uavdt-other", "role, version"),
        ("source_group_id", "M0029", "selection"),
        ("frame_number", "11", "selection"),
        ("asset_id", "renamed", "identity"),
        ("evaluation_image_path", "../outside.jpg", "identity"),
        ("target_classes", "car_or_van;person", "targets only"),
        ("width", "9", "dimensions"),
    ],
)
def test_manifest_semantics_are_checked_even_if_receipt_is_updated(
    tmp_path, prepared, field, value, message
):
    modify_manifest(tmp_path, lambda rows: rows[0].update({field: value}))
    with pytest.raises(ValueError, match=message):
        readiness.validate_uavdt_evaluation(tmp_path, prepared)


def test_repeated_frame_and_duplicate_media_are_rejected(tmp_path, prepared):
    modify_manifest(
        tmp_path, lambda rows: rows[1].update(image_sha256=rows[0]["image_sha256"])
    )
    with pytest.raises(ValueError, match="duplicate image"):
        readiness.validate_uavdt_evaluation(tmp_path, prepared)
    modify_manifest(tmp_path, lambda rows: rows.__setitem__(1, rows[0].copy()))
    with pytest.raises(ValueError, match="selection"):
        readiness.validate_uavdt_evaluation(tmp_path, prepared)


@pytest.mark.parametrize(
    "relative",
    [
        "GT/M0001_gt_whole.txt",
        "GT/M0001_gt_ignore.txt",
        "attributes/train/M0001_attr.txt",
        "images/M0001/img000001.jpg",
    ],
)
def test_changed_native_files_or_images_fail(tmp_path, prepared, relative):
    (tmp_path / readiness.DATA_DIRECTORY / relative).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        readiness.validate_uavdt_evaluation(tmp_path, prepared)


def test_changed_canonical_labels_fail_even_with_new_receipt(tmp_path, prepared):
    path = tmp_path / readiness.ANNOTATIONS_PATH
    labels = json.loads(path.read_text())
    labels["annotations"].pop()
    write_json(path, labels)
    refresh_receipt(tmp_path)
    with pytest.raises(ValueError, match="unmodified native labels"):
        readiness.validate_uavdt_evaluation(tmp_path, prepared)


def test_unrecorded_manifest_change_and_wrong_checkpoint_fail(tmp_path, prepared):
    path = tmp_path / readiness.MANIFEST_PATH
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="recorded identity"):
        readiness.validate_uavdt_evaluation(tmp_path, prepared)
    path.write_bytes(original)
    (tmp_path / prepared.model.weights_path).write_bytes(b"other checkpoint")
    with pytest.raises(ValueError, match="checkpoint checksum"):
        readiness.validate_uavdt_evaluation(tmp_path, prepared)


def test_missing_preparation_record_does_not_imply_readiness(tmp_path, source):
    with pytest.raises(FileNotFoundError):
        readiness.validate_uavdt_evaluation(tmp_path, source)


def test_validator_cli_reports_missing_data_without_traceback(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_uavdt_evaluation.py",
            "--repository-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "UAVDT baseline is not ready" in result.stderr
    assert "Traceback" not in result.stderr
