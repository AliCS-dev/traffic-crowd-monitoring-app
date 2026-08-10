import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_training_experiment_record_matches_tracked_configuration():
    record_path = PROJECT_ROOT / "data/evaluation/training_experiments.json"
    values = json.loads(record_path.read_text(encoding="utf-8"))

    assert values["schema_version"] == 1
    assert len(values["experiments"]) == 1
    experiment = values["experiments"][0]
    config = experiment["training_config"]
    assert sha256(PROJECT_ROOT / config["path"]) == config["sha256"]
    assert experiment["dataset"]["source_group_overlap"] == 0
    assert experiment["dataset"]["held_out_test_used"] is False
    assert experiment["training_result"]["selected_epoch"] == 2
    assert experiment["status"] == "completed_rejected"


def test_starting_checkpoint_identity_matches_candidate_registry():
    experiment_values = json.loads(
        (PROJECT_ROOT / "data/evaluation/training_experiments.json").read_text(
            encoding="utf-8"
        )
    )
    candidate_values = json.loads(
        (PROJECT_ROOT / "configs/evaluation/aerial_model_candidates.json").read_text(
            encoding="utf-8"
        )
    )
    experiment = experiment_values["experiments"][0]
    candidate = next(
        item
        for item in candidate_values["candidates"]
        if item["candidate_id"] == "yolo26m-visdrone"
    )

    assert experiment["starting_checkpoint"]["sha256"] == candidate["weights_sha256"]
    assert (
        experiment["starting_checkpoint"]["revision"]
        == candidate["repository_revision"]
    )
