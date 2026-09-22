"""Export an allowlisted Docker identity and measured backend environment."""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def docker_json(*arguments):
    return json.loads(
        subprocess.check_output(["docker", *arguments], text=True, timeout=60)
    )


def export_manifest(container):
    inspection = docker_json("inspect", "--type", "container", container)[0]
    if not inspection["State"]["Running"]:
        raise ValueError("The backend container must be running.")
    runtime = docker_json("exec", container, "python", "-m", "app.runtime_provenance")
    image = docker_json("image", "inspect", inspection["Image"])[0]
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "container_id": inspection["Id"],
        "image_id": image["Id"],
        "image_repo_digests": image.get("RepoDigests") or [],
        "runtime": runtime,
        "scope": "backend; separate process snapshot in the running container",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = export_manifest(args.container)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(f"Recorded {record['image_id']} in {args.output}")


if __name__ == "__main__":
    main()
