import csv
import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from evaluation import remote_zip
from evaluation import uavdt_source_audit as audit


def zipped(files):
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return stream.getvalue()


def test_member_comparison_checks_bytes_not_only_name():
    with ZipFile(io.BytesIO(zipped({"a.txt": b"same"}))) as archive:
        assert audit.compare_member(archive, "a.txt", b"same")[
            "sha256"
        ] == audit.sha256(b"same")
        with pytest.raises(ValueError, match="differs"):
            audit.compare_member(archive, "a.txt", b"changed")
        with pytest.raises(ValueError, match="Missing"):
            audit.compare_member(archive, "missing", b"")


def test_task_comparison_uses_geometry_not_different_final_fields():
    det = b"1,1,10,20,30,40,2,3,1\n2,1,11,20,30,40,2,3,1\n"
    mot = b"2,1,11,20,30,40,1,1,-1\n1,1,10,20,30,40,1,1,-1\n"
    result = audit.sequence_diagnostics(det, mot)
    assert result["detection_and_tracking_geometry_equal"] is True
    assert result["unique_detection_track_ids"] == 1
    assert result["native_category_counts"] == {1: 2}
    assert (
        audit.sequence_diagnostics(det, mot.replace(b"11,20", b"12,20"))[
            "detection_and_tracking_geometry_equal"
        ]
        is False
    )


@pytest.mark.parametrize("payload", [b"", b"1,2,3\n", b"1,1,1,1,1,1,1,1,1\n" * 2])
def test_task_comparison_rejects_invalid_rows(payload):
    with pytest.raises(ValueError):
        audit.sequence_diagnostics(payload, payload)


def image_rows():
    return [
        {
            "source_group_id": sequence,
            "frame_number": str(frame),
            "source_split": "train",
        }
        for sequence in ("M0207", "M0402")
        for frame in range(1, 11)
    ]


@pytest.mark.parametrize("failure", ["test", "duplicate", "missing", "wrong_sequence"])
def test_image_scope_rejects_expansion_or_held_out_data(failure):
    rows = image_rows()
    if failure == "test":
        rows[0]["source_split"] = "test"
    elif failure == "duplicate":
        rows[0] = rows[1].copy()
    elif failure == "missing":
        rows.pop()
    else:
        rows[0]["source_group_id"] = "M0208"
    with pytest.raises(ValueError, match="training frames"):
        audit.questioned_images(rows)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    def write(path, payload):
        path = tmp_path / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    readme = b"Synthetic source format documentation"
    files = {"UAV-benchmark-MOTD_v1.0/README.md": readme}
    protocol = {"sequences": [{"sequence": s} for s in ("M0207", "M0402")]}
    for item in protocol["sequences"]:
        for suffix, payload in (
            ("_whole", b"1,1,10,20,30,40,1,1,1\n"),
            ("_ignore", b""),
            ("", b"1,1,10,20,30,40,1,1,-1\n"),
        ):
            filename = item["sequence"] + "_gt" + suffix + ".txt"
            files["UAV-benchmark-MOTD_v1.0/GT/" + filename] = payload
            write(audit.DATA_DIRECTORY / "GT" / filename, payload)
    toolkit = zipped(files)
    rows = image_rows()
    media_files = {}
    for row in rows:
        sequence, frame = row["source_group_id"], int(row["frame_number"])
        member = f"UAV-benchmark-M/{sequence}/img{frame:06d}.jpg"
        payload = member.encode()  # Byte equality is independent of image decoding.
        media_files[member] = payload
        row.update(
            asset_id=f"uavdt_{sequence}_{frame:06d}",
            evaluation_image_path=f"data/{sequence}/{frame}.jpg",
            image_sha256=audit.sha256(payload),
        )
        write(row["evaluation_image_path"], payload)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    write(audit.MANIFEST_PATH, buffer.getvalue().encode())
    write(audit.PROTOCOL_PATH, json.dumps(protocol).encode())
    write(
        audit.BASELINE_PATH,
        json.dumps(
            {
                "provenance": {"source_evaluation_readiness": {"ready": True}},
                "source_manifest_sha256": "baseline-manifest",
            }
        ).encode(),
    )
    write(
        audit.EVIDENCE_PATH,
        json.dumps(
            {
                "uavdt": {
                    "downloaded_ranges": [
                        {
                            "offset": 0,
                            "bytes": len(toolkit),
                            "sha256": audit.sha256(toolkit),
                        }
                    ],
                    "toolkit_readme_sha256": audit.sha256(readme),
                }
            }
        ).encode(),
    )
    media = zipped(media_files)
    monkeypatch.setattr(audit, "TOOLKIT_SIZE", len(toolkit))
    monkeypatch.setattr(audit, "MEDIA_SIZE", len(media))
    monkeypatch.setattr(audit, "load_protocol", lambda _: protocol)
    monkeypatch.setattr(audit, "load_evaluation_config", lambda _: None)
    monkeypatch.setattr(audit, "validate_uavdt_evaluation", lambda *_: {"ready": True})
    requests = []

    def request(req, timeout):
        requests.append(req.full_url)
        payload = toolkit if audit.TOOLKIT_URL in req.full_url else media
        start, end = map(int, req.headers["Range"].removeprefix("bytes=").split("-"))
        response = io.BytesIO(payload[start : end + 1])
        response.status = 206
        response.headers = {"Content-Range": f"bytes {start}-{end}/{len(payload)}"}
        return response

    monkeypatch.setattr(remote_zip, "urlopen", request)
    return tmp_path, requests


def test_complete_audit_keeps_inputs_unchanged_and_logs_transfers(fixture):
    root, requests = fixture
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    output = audit.audit_sources(root, progress=lambda _: None)
    report = json.loads((output / "audit.json").read_text())
    assert len(report["image_members"]) == 20
    assert len(report["annotation_members"]) == 4
    assert report["all_requested_members_equal"] is True
    assert report["full_archive_equivalence_verified"] is False
    assert report["test_images_downloaded"] is False
    assert report["annotations_changed"] is False
    assert requests
    assert all(path.read_bytes() == payload for path, payload in before.items())
    assert all(
        item["downloaded_bytes"] > 0
        for item in json.loads((output / "download_attempt.json").read_text())
    )


def test_changed_readiness_rejected_before_network_or_output(fixture, monkeypatch):
    root, requests = fixture
    monkeypatch.setattr(audit, "validate_uavdt_evaluation", lambda *_: {"ready": False})
    with pytest.raises(ValueError, match="Frozen inputs"):
        audit.audit_sources(root)
    assert not requests
    assert not (root / audit.OUTPUT_PATH).exists()


def test_mismatch_retains_attempt_but_never_writes_success(fixture):
    root, _ = fixture
    path = root / audit.DATA_DIRECTORY / "GT/M0207_gt_whole.txt"
    path.write_bytes(b"different")
    with pytest.raises(ValueError, match="Publisher member differs"):
        audit.audit_sources(root, progress=lambda _: None)
    assert len(list((root / audit.OUTPUT_PATH).glob("*/download_attempt.json"))) == 1
    assert not list((root / audit.OUTPUT_PATH).glob("*/audit.json"))
