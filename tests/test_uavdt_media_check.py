import hashlib
import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np
import pytest

from evaluation import remote_zip
from evaluation import uavdt_media_check as media_check


def archive_bytes(files):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class Response(io.BytesIO):
    def __init__(self, data, start, end, total, status=206):
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Range": f"bytes {start}-{end}/{total}"}


def fake_http(monkeypatch, archives):
    def request(req, timeout):
        payload = archives[req.full_url.split("?")[0]]
        start, end = map(int, req.headers["Range"].removeprefix("bytes=").split("-"))
        return Response(payload[start : end + 1], start, end, len(payload))

    monkeypatch.setattr(remote_zip, "urlopen", request)


def test_range_reader_works_with_standard_zipfile_and_cached_reads(monkeypatch):
    payload = archive_bytes({"test.txt": b"hello"})
    fake_http(monkeypatch, {"https://example.test/file.zip": payload})
    reader = remote_zip.HTTPRangeReader("https://example.test/file.zip", len(payload))
    with ZipFile(reader) as archive:
        assert archive.read("test.txt") == b"hello"
    total = reader.downloaded_bytes
    reader.seek(0)
    assert reader.read(5) == payload[:5]
    assert reader.downloaded_bytes == total
    reader.seek(0, 2)
    assert reader.read() == b""


@pytest.mark.parametrize(
    "case", ["full_response", "wrong_range", "truncated", "oversized"]
)
def test_range_reader_rejects_wrong_server_responses(monkeypatch, case):
    response = Response(b"abc", 0, 2, 10)
    if case == "full_response":
        response.status = 200
    elif case == "wrong_range":
        response.headers["Content-Range"] = "bytes 1-3/10"
    elif case == "truncated":
        response = Response(b"ab", 0, 2, 10)
    else:
        response = Response(b"abcd", 0, 2, 10)
    monkeypatch.setattr(remote_zip, "urlopen", lambda *a, **k: response)
    reader = remote_zip.HTTPRangeReader("https://example.test/file.zip", 10)
    with pytest.raises(ValueError, match="range|length"):
        reader.read(3)
    assert reader.downloaded_bytes == 0


def test_range_budget_refuses_unbounded_archive_download(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Budget must be checked before any network request")

    monkeypatch.setattr(remote_zip, "urlopen", forbidden)
    reader = remote_zip.HTTPRangeReader(
        "https://example.test/file.zip", 100, byte_budget=10
    )
    with pytest.raises(ValueError, match="budget"):
        reader.read()
    with pytest.raises(ValueError, match="Negative"):
        reader.seek(-1)


@pytest.mark.parametrize("frames", [set(), {0, 1}, {1, 3}])
def test_frame_selection_rejects_missing_or_zero_based_frames(frames):
    with pytest.raises(ValueError, match="contiguous"):
        media_check.selected_frames(frames)


def test_frame_selection_is_deterministic():
    assert media_check.selected_frames(set(range(1, 408))) == (1, 204, 407)


@pytest.mark.parametrize(
    "split,flags", [("test", (1, 0, 0)), ("train", (0, 1, 0)), ("train", (1, 0, 1))]
)
def test_test_night_and_fog_media_cannot_be_selected(split, flags):
    with pytest.raises(ValueError, match="training"):
        media_check.require_training_daytime(
            {
                "split": split,
                "attributes": dict(
                    zip(("daylight", "night", "fog"), flags, strict=True)
                ),
            }
        )


def test_member_limit_and_missing_members_fail():
    with ZipFile(io.BytesIO(archive_bytes({"data": b"abc"}))) as archive:
        with pytest.raises(ValueError, match="limit"):
            media_check.read_member(archive, "data", limit=2)
        with pytest.raises(ValueError, match="Missing"):
            media_check.read_member(archive, "missing")


@pytest.fixture
def source_fixture(tmp_path, monkeypatch):
    attrs, gt, images, sequences = {}, {}, {}, []

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    for index, seq in enumerate(media_check.SEQUENCES):
        attr_path = f"M_attr/train/{seq}_attr.txt"
        attrs[attr_path] = b"1,0,0,0,1,0,1,0,0,0\n"
        whole = "".join(
            f"{f},1,10,10,10,10,1,1,{index + 1}\n" for f in (1, 2, 3)
        ).encode()
        ignored = b"1,2,40,10,20,20,1,-1,-1\n"
        gt[f"UAV-benchmark-MOTD_v1.0/GT/{seq}_gt_whole.txt"] = whole
        gt[f"UAV-benchmark-MOTD_v1.0/GT/{seq}_gt_ignore.txt"] = ignored
        sequences.append(
            {
                "sequence": seq,
                "source_split": "train",
                "attribute_member": attr_path,
                "attribute_sha256": digest(attrs[attr_path]),
                "detection_sha256": digest(whole),
                "ignore_sha256": digest(ignored),
            }
        )
        for frame in (1, 2, 3):
            image = np.full((80, 100, 3), index * 40 + frame * 15, dtype=np.uint8)
            success, encoded = cv2.imencode(".jpg", image)
            assert success
            images[f"UAV-benchmark-M/{seq}/img{frame:06d}.jpg"] = encoded.tobytes()
    retained = tmp_path / "data/evaluation/raw/source_inspection_20261007/uavdt"
    retained.mkdir(parents=True)
    attr_payload = archive_bytes(attrs)
    (retained / "M_attr.zip").write_bytes(attr_payload)
    evidence = {
        "uavdt": {"attribute_zip_sha256": digest(attr_payload), "sequences": sequences}
    }
    (tmp_path / "data/evaluation/annotation_feasibility_v2.json").write_text(
        json.dumps(evidence)
    )
    gt_zip, media_zip = archive_bytes(gt), archive_bytes(images)
    monkeypatch.setattr(media_check, "TOOLKIT_SIZE", len(gt_zip))
    monkeypatch.setattr(media_check, "MEDIA_SIZE", len(media_zip))
    fake_http(
        monkeypatch,
        {
            f"{media_check.BASE_URL}/UAV-benchmark-MOTD_v1.0.zip": gt_zip,
            f"{media_check.BASE_URL}/UAV-benchmark-M.zip": media_zip,
        },
    )
    return tmp_path


def test_media_check_converts_real_pipeline_and_emits_only_inspection_evidence(
    source_fixture,
):
    report = media_check.check_media(source_fixture)
    assert len(report["frames"]) == 9
    assert report["test_media_downloaded"] is False
    assert report["model_inference_run"] is False
    assert report["duplicate_image_hashes"] == 0
    assert all(frame["dataset_role"] == "training" for frame in report["frames"])
    assert all(frame["out_of_bounds_boxes"] == 0 for frame in report["frames"])
    preview = source_fixture / report["frames"][0]["overlay_path"]
    image = cv2.imread(str(preview))
    assert image.shape == (125, 100, 3)
    assert tuple(image[10, 10]) == (230, 80, 40)
    with pytest.raises(FileExistsError):
        media_check.check_media(source_fixture)


def test_output_cannot_overwrite_historical_evidence(tmp_path):
    from pathlib import Path

    with pytest.raises(ValueError, match="data/evaluation/raw"):
        media_check.check_media(tmp_path, Path("data/evaluation/manifest.csv"))


@pytest.mark.parametrize(
    "field,value", [("source_split", "test"), ("attribute_sha256", "incorrect")]
)
def test_untrusted_source_metadata_fails_before_media_access(
    source_fixture, monkeypatch, field, value
):
    path = source_fixture / "data/evaluation/annotation_feasibility_v2.json"
    evidence = json.loads(path.read_text())
    evidence["uavdt"]["sequences"][0][field] = value
    path.write_text(json.dumps(evidence))

    def forbidden(*args, **kwargs):
        pytest.fail("No remote media may be read for rejected source metadata")

    monkeypatch.setattr(remote_zip, "urlopen", forbidden)
    with pytest.raises(ValueError, match="Held-out|checksum"):
        media_check.check_media(source_fixture)
