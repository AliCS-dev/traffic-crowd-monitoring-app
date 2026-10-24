"""Compare the frozen UAVDT inputs with publisher-hosted release members."""

import argparse
import csv
import io
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from evaluation.evaluation_config import load_evaluation_config
from evaluation.remote_zip import HTTPRangeReader
from evaluation.uavdt_media_check import MEDIA_SIZE, TOOLKIT_SIZE, read_member, sha256
from evaluation.uavdt_readiness import (
    CONFIG_PATH,
    DATA_DIRECTORY,
    EVIDENCE_PATH,
    MANIFEST_PATH,
    PROTOCOL_PATH,
    file_sha256,
    load_protocol,
    validate_uavdt_evaluation,
)

PUBLISHER_PAGE = "https://sites.google.com/view/grli-uavdt/"
DOWNLOAD = "https://drive.usercontent.google.com/download?export=download&confirm=t&id="
TOOLKIT_URL = DOWNLOAD + "19498uJd7T9w4quwnQEy62nibt3uyT9pq"
MEDIA_URL = DOWNLOAD + "1m8KA6oPIRK_Iwt9TYFquC87vBc_8wRVc"
QUESTIONED_SEQUENCES = frozenset({"M0207", "M0402"})
BASELINE_PATH = Path("data/evaluation/uavdt_daytime_baseline.json")
OUTPUT_PATH = Path("data/evaluation/derived/uavdt_source_audit")


def compare_member(archive: ZipFile, name: str, expected: bytes) -> dict:
    payload = read_member(archive, name, limit=8_000_000)
    if payload != expected:
        raise ValueError(f"Publisher member differs from frozen local input: {name}")
    return {"member": name, "bytes": len(payload), "sha256": sha256(payload)}


def sequence_diagnostics(detection: bytes, tracking: bytes) -> dict:
    def rows(payload):
        result = [
            tuple(map(int, row))
            for row in csv.reader(io.StringIO(payload.decode("utf-8")))
            if row
        ]
        if not result or any(len(row) != 9 for row in result):
            raise ValueError("Expected nonempty nine-column source annotations")
        if len({row[:2] for row in result}) != len(result):
            raise ValueError("Duplicate source frame/track identity")
        return result

    det, mot = rows(detection), rows(tracking)
    return {
        "detection_rows": len(det),
        "tracking_rows": len(mot),
        "unique_detection_track_ids": len({row[1] for row in det}),
        "native_category_counts": dict(sorted(Counter(row[8] for row in det).items())),
        "detection_frame_min": min(row[0] for row in det),
        "detection_frame_max": max(row[0] for row in det),
        "detection_and_tracking_geometry_equal": Counter(row[:6] for row in det)
        == Counter(row[:6] for row in mot),
        "tracking_sha256": sha256(tracking),
    }


def questioned_images(rows: list[dict]) -> list[dict]:
    selected = [row for row in rows if row["source_group_id"] in QUESTIONED_SEQUENCES]
    identities = {(row["source_group_id"], row["frame_number"]) for row in selected}
    if (
        len(selected) != 20
        or len(identities) != 20
        or Counter(row["source_group_id"] for row in selected)
        != {"M0207": 10, "M0402": 10}
        or any(row["source_split"] != "train" for row in selected)
    ):
        raise ValueError(
            "Expected ten distinct training frames per questioned sequence"
        )
    return selected


def audit_sources(root: Path, *, progress=print) -> Path:
    root = root.resolve()
    protocol = load_protocol(root)
    baseline = json.loads((root / BASELINE_PATH).read_text(encoding="utf-8"))
    readiness = validate_uavdt_evaluation(
        root, load_evaluation_config(root / CONFIG_PATH)
    )
    if readiness != baseline["provenance"]["source_evaluation_readiness"]:
        raise ValueError("Frozen inputs differ from the completed baseline")
    with (root / MANIFEST_PATH).open(encoding="utf-8", newline="") as handle:
        selected = questioned_images(list(csv.DictReader(handle)))
    evidence = json.loads((root / EVIDENCE_PATH).read_text(encoding="utf-8"))["uavdt"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = root / OUTPUT_PATH / f"{stamp}-publisher-comparison"
    output.mkdir(parents=True, exist_ok=False)
    toolkit = HTTPRangeReader(TOOLKIT_URL, TOOLKIT_SIZE, byte_budget=9_000_000)
    media = HTTPRangeReader(MEDIA_URL, MEDIA_SIZE, byte_budget=24_000_000)
    report = {
        "schema_version": 1,
        "record_type": "publisher_member_comparison_not_accuracy",
        "created_at_utc": stamp,
        "publisher_page": PUBLISHER_PAGE,
        "audit_code_sha256": file_sha256(Path(__file__)),
        "baseline_record_sha256": file_sha256(root / BASELINE_PATH),
        "protocol_sha256": file_sha256(root / PROTOCOL_PATH),
        "source_manifest_sha256": baseline["source_manifest_sha256"],
        "baseline_readiness_unchanged": True,
        "new_inference_run": False,
        "annotations_changed": False,
        "test_images_downloaded": False,
        "full_archive_equivalence_verified": False,
        "human_annotation_review": False,
        "annotation_members": [],
        "image_members": [],
        "sequence_diagnostics": {},
    }
    try:
        # Reuse the two recorded ranges, including the README and ZIP directory.
        for item in evidence["downloaded_ranges"]:
            progress(f"Comparing publisher toolkit range at {item['offset']}.")
            toolkit.seek(item["offset"])
            payload = toolkit.read(item["bytes"])
            if sha256(payload) != item["sha256"]:
                raise ValueError("Publisher toolkit range differs from recorded mirror")
        with ZipFile(toolkit) as archive:
            readme = read_member(archive, "UAV-benchmark-MOTD_v1.0/README.md")
            if sha256(readme) != evidence["toolkit_readme_sha256"]:
                raise ValueError("Publisher README differs from recorded mirror")
            report["toolkit_readme_sha256"] = sha256(readme)
            for item in protocol["sequences"]:
                sequence = item["sequence"]
                for suffix in ("whole", "ignore"):
                    filename = f"{sequence}_gt_{suffix}.txt"
                    local = root / DATA_DIRECTORY / "GT" / filename
                    report["annotation_members"].append(
                        compare_member(
                            archive,
                            f"UAV-benchmark-MOTD_v1.0/GT/{filename}",
                            local.read_bytes(),
                        )
                    )
                if sequence in QUESTIONED_SEQUENCES:
                    prefix = f"UAV-benchmark-MOTD_v1.0/GT/{sequence}"
                    report["sequence_diagnostics"][sequence] = sequence_diagnostics(
                        read_member(archive, f"{prefix}_gt_whole.txt"),
                        read_member(archive, f"{prefix}_gt.txt"),
                    )
        progress("Comparing publisher images for M0207 and M0402 only.")
        with ZipFile(media) as archive:
            for row in selected:
                sequence, frame = row["source_group_id"], int(row["frame_number"])
                local = root / row["evaluation_image_path"]
                expected = local.read_bytes()
                if sha256(expected) != row["image_sha256"]:
                    raise ValueError("Local image changed during source audit")
                member = f"UAV-benchmark-M/{sequence}/img{frame:06d}.jpg"
                record = compare_member(archive, member, expected)
                report["image_members"].append({"asset_id": row["asset_id"], **record})
                progress(f"Verified {row['asset_id']} against publisher bytes.")
        report["all_requested_members_equal"] = True
        (output / "audit.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    finally:
        (output / "download_attempt.json").write_text(
            json.dumps(
                [
                    {
                        "url": reader.url,
                        "downloaded_bytes": reader.downloaded_bytes,
                        "byte_budget": reader.byte_budget,
                        "ranges": reader.requests,
                    }
                    for reader in (toolkit, media)
                ],
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    output = audit_sources(Path(__file__).resolve().parents[1])
    print(f"Publisher comparison saved: {output}")


if __name__ == "__main__":
    main()
