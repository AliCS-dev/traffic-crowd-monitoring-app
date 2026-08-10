import json
from pathlib import Path

from evaluation.evaluation_config import load_evaluation_config
from evaluation.model_candidates import load_model_candidate_selection

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATION_CONFIG = Path("configs/evaluation/yolo26m_visdrone_validation.json")
HELD_OUT_CONFIG = Path("configs/evaluation/yolo26m_visdrone_held_out_test.json")
SELECTION_RECORD = Path("configs/evaluation/final_model_selection.json")
CANDIDATE_SELECTION = Path("configs/evaluation/aerial_model_candidates.json")


def test_held_out_config_matches_selected_validation_settings():
    validation = load_evaluation_config(VALIDATION_CONFIG)
    held_out = load_evaluation_config(HELD_OUT_CONFIG)

    assert held_out.dataset.role == "held_out_test"
    assert held_out.dataset.version == validation.dataset.version
    assert held_out.dataset.manifest_path == validation.dataset.manifest_path
    assert held_out.model == validation.model
    assert held_out.inference == validation.inference
    assert held_out.metrics == validation.metrics
    assert held_out.timing == validation.timing
    assert held_out.protocol_version == validation.protocol_version
    assert held_out.random_seed == validation.random_seed
    assert held_out.output_directory == validation.output_directory


def test_final_selection_record_matches_config_and_candidate_registry():
    values = json.loads((PROJECT_ROOT / SELECTION_RECORD).read_text(encoding="utf-8"))
    config = load_evaluation_config(HELD_OUT_CONFIG)
    candidates = load_model_candidate_selection(CANDIDATE_SELECTION)
    candidate = next(
        item
        for item in candidates.candidates
        if item.candidate_id == values["selected_candidate_id"]
    )

    assert values["status"] == "frozen_for_held_out_test"
    assert values["held_out_predictions_available_at_freeze"] is False
    assert values["held_out_evaluation_config"] == HELD_OUT_CONFIG.as_posix()
    assert values["checkpoint"]["path"] == config.model.weights_path.as_posix()
    assert values["checkpoint"]["sha256"] == candidate.weights_sha256
    assert values["checkpoint"]["size_bytes"] == candidate.weights_size_bytes
    assert values["class_mapping"] == config.model.class_mapping.as_dict()
    assert values["inference"] == {
        "confidence_floor": config.inference.confidence_floor,
        "operating_confidence": config.inference.operating_confidence,
        "image_size": config.inference.image_size,
        "scale_factor": config.inference.scale_factor,
        "device": config.inference.device,
        "max_detections": config.inference.max_detections,
        "batch_size": config.inference.batch_size,
        "numeric_precision": config.inference.numeric_precision,
    }
