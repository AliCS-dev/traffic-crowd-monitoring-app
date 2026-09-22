"""Require current development regression evidence for backend dependency PRs."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.runtime_provenance import source_digest
from app.schemas.monitoring import RuntimeProvenanceResult
from evaluation.runtime_regression import compare_records

DATA = Path("data/runtime-regression")
RUNTIME_FILES = {"Dockerfile", "requirements.txt", "requirements-container.txt"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_evidence(root):
    directory = root / DATA
    baseline_path = directory / "baseline.json"
    reference = json.loads(baseline_path.read_text())
    candidate = json.loads((directory / "latest.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    runtime = RuntimeProvenanceResult.model_validate(candidate["runtime"])
    if runtime.source_sha256 != source_digest(root):
        raise ValueError("Regression evidence does not match the backend source.")
    if not runtime.application_commit or runtime.source_dirty is not False:
        raise ValueError("Evidence requires an identified, clean backend build.")
    for line in (root / "requirements-container.txt").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        version = runtime.dependencies.get(canonicalize_name(requirement.name))
        if version is None or version not in requirement.specifier:
            raise ValueError(f"Evidence does not match dependency {requirement.name}.")
    if candidate["baseline_sha256"] != sha256(baseline_path):
        raise ValueError("Evidence does not refer to the committed baseline.")
    if candidate["manifest_sha256"] != sha256(directory / "manifest.json"):
        raise ValueError("Fixture manifest changed; rerun regression checks.")
    expected = set()
    for fixture in manifest["fixtures"]:
        if sha256(directory / "fixtures" / fixture["name"]) != fixture["sha256"]:
            raise ValueError("Fixture bytes do not match their manifest.")
        numbers = [0] if fixture["kind"] == "image" else [0, 10, 20]
        expected.update(f"{fixture['name']}:{number}" for number in numbers)
    if not expected or set(candidate["frames"]) != expected:
        raise ValueError("Regression evidence has incomplete frame coverage.")
    if not any(frame["detections"] for frame in candidate["frames"].values()):
        raise ValueError("Regression evidence contains no detections.")
    differences = compare_records(reference, candidate, manifest["tolerances"])
    if differences or candidate["status"] != "pass" or candidate["differences"]:
        raise ValueError(f"Changed results require review: {differences}")


def check_base(root, base_ref):
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=root,
            text=True,
        ).splitlines()
    )
    if not changed.intersection(RUNTIME_FILES):
        return False
    # Existing references cannot be weakened in the dependency-update PR itself.
    for filename in ("baseline.json", "manifest.json"):
        relative = (DATA / filename).as_posix()
        previous = subprocess.run(
            ["git", "show", f"{base_ref}:{relative}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if (
            previous.returncode == 0
            and previous.stdout != (root / relative).read_bytes()
        ):
            raise ValueError(
                "Reference changed with dependencies; review a separate baseline PR."
            )
    validate_evidence(root)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref")
    args = parser.parse_args()
    try:
        if args.base_ref:
            checked = check_base(ROOT, args.base_ref)
        else:
            validate_evidence(ROOT)
            checked = True
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Runtime regression evidence failed: {error}", file=sys.stderr)
        return 1
    print("Runtime regression evidence passed." if checked else "No runtime update.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
