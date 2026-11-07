"""Run inside the isolated test backend, through the real Nginx proxy."""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from serve import controlled_profile

from app.crowd_analysis import load_dense_crowd_analysis_decision
from app.database.video_job_repository import create_video_analysis_job

EVIDENCE = Path("/tmp/controlled-compose-evidence.json")


def read_result(client, session_id, frame_count):
    response = client.get(f"/api/analyses/{session_id}")
    response.raise_for_status()
    result = response.json()
    assert result["status"] == "completed"
    assert result["model_profile"]["model_id"] == "controlled-compose-test"
    assert result["model_profile"]["quality_gate_status"] == "not_evaluated"
    assert result["dense_crowd_analysis"]["status"] == "unsupported"
    assert result["dense_crowd_analysis"]["count"] is None
    assert len(result["frames"]) == frame_count
    hashes = {}
    for frame in result["frames"]:
        assert len(frame["detections"]) == 1
        assert sum(row["object_count"] for row in frame["frame_summaries"]) == 1
        assert len(frame["grid_cells"]) == 6
        assert (
            sum(
                row["object_count"]
                for cell in frame["grid_cells"]
                for row in cell["summaries"]
            )
            == 1
        )
        assert frame["source_asset"]["rendered_overlays"] == []
        for variant in ("source_asset", "visual_asset"):
            url = frame[variant]["url"]
            media = client.get(url)
            media.raise_for_status()
            assert media.headers["content-type"] == "image/jpeg"
            assert media.content.startswith(b"\xff\xd8")
            hashes[url] = hashlib.sha256(media.content).hexdigest()
    return {"session_id": session_id, "frame_count": frame_count, "assets": hashes}


def create_workflows(client):
    rejected = client.post(
        "/api/analyses/images",
        files={"image": ("invalid.jpg", b"not an image", "image/jpeg")},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "invalid_image"
    saved = []
    for kind, name, mime, frames in (
        ("image", "roundabout_6.png", "image/png", 1),
        ("video", "roundabout_sequence.avi", "video/x-msvideo", 3),
    ):
        with (Path("/fixtures") / name).open("rb") as handle:
            response = client.post(
                f"/api/analyses/{kind}s",
                files={kind: (name, handle, mime)},
                data={
                    "session_name": "controlled-compose-test",
                    "grid_rows": "2",
                    "grid_columns": "3",
                },
            )
        assert response.status_code == (201 if kind == "image" else 202)
        session_id = response.json()["session_id"]
        if kind == "video":
            deadline = time.monotonic() + 60
            while True:
                status = client.get(f"/api/analyses/videos/{session_id}")
                status.raise_for_status()
                job = status.json()
                assert job["status"] != "failed", job
                if job["status"] == "completed":
                    assert job["sampled_frames_processed"] == 3
                    break
                assert time.monotonic() < deadline, "Video completion timed out"
                time.sleep(0.1)
        saved.append(read_result(client, session_id, frames))
    # This queued job has no worker. Startup must mark it interrupted, not resume it.
    abandoned = create_video_analysis_job(
        video_path=Path("/fixtures/roundabout_sequence.avi"),
        original_filename="controlled-interruption.avi",
        session_name="controlled-interruption",
        sampling_interval_seconds=1,
        grid_rows=None,
        grid_columns=None,
        total_source_frames=3,
        sampled_frames_total=3,
        model_profile=controlled_profile(),
        crowd_analysis_decision=load_dense_crowd_analysis_decision(),
    )
    evidence = {"saved": saved, "interrupted_session_id": abandoned.session_id}
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def verify_saved(client):
    evidence = json.loads(EVIDENCE.read_text())
    for saved in evidence["saved"]:
        assert read_result(client, saved["session_id"], saved["frame_count"]) == saved
    session_id = evidence["interrupted_session_id"]
    job = client.get(f"/api/analyses/videos/{session_id}").json()
    assert job["status"] == "failed"
    assert job["failure_code"] == "worker_interrupted"
    assert client.get(f"/api/analyses/{session_id}").json()["status"] == "failed"
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-saved", action="store_true")
    args = parser.parse_args()
    if os.getenv("CONTROLLED_COMPOSE_TEST") != "1":
        raise RuntimeError("Use only the isolated Compose test override.")
    with httpx.Client(
        base_url="http://frontend:8080", timeout=30, trust_env=False
    ) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/ready").json()["status"] == "ready"
        assert 'id="root"' in client.get("/workspace").text
        evidence = (
            verify_saved(client) if args.verify_saved else create_workflows(client)
        )
        history = client.get("/api/analyses?page=1&page_size=20").json()
        assert {row["session_id"] for row in evidence["saved"]} <= {
            row["id"] for row in history["items"]
        }
    print(
        json.dumps({"status": "passed", "verify_saved": args.verify_saved, **evidence})
    )


if __name__ == "__main__":
    main()
