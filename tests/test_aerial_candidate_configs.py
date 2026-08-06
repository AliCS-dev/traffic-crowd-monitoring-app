from pathlib import Path

from evaluation.confidence_sweep import load_confidence_sweep_config
from evaluation.evaluation_config import load_evaluation_config
from evaluation.model_candidates import load_model_candidate_selection

BASELINE_CONFIG = Path("configs/evaluation/yolo26n_selected_validation.json")
CANDIDATE_SELECTION = Path("configs/evaluation/aerial_model_candidates.json")
CANDIDATE_CONFIGS = {
    "yolo26m-visdrone": Path("configs/evaluation/yolo26m_visdrone_validation.json"),
    "yolo11x-visdrone": Path("configs/evaluation/yolo11x_visdrone_validation.json"),
}
SWEEP_CONFIGS = {
    "yolo26m-visdrone": Path(
        "configs/evaluation/yolo26m_visdrone_confidence_sweep.json"
    ),
    "yolo11x-visdrone": Path(
        "configs/evaluation/yolo11x_visdrone_confidence_sweep.json"
    ),
}


def test_candidate_evaluations_match_the_frozen_baseline_protocol():
    baseline = load_evaluation_config(BASELINE_CONFIG)
    selection = load_model_candidate_selection(CANDIDATE_SELECTION)

    assert set(CANDIDATE_CONFIGS) == {
        candidate.candidate_id for candidate in selection.candidates
    }
    for candidate in selection.candidates:
        config = load_evaluation_config(CANDIDATE_CONFIGS[candidate.candidate_id])

        assert config.protocol_version == baseline.protocol_version
        assert config.random_seed == baseline.random_seed
        assert config.dataset == baseline.dataset
        assert config.inference == baseline.inference
        assert config.metrics == baseline.metrics
        assert config.timing == baseline.timing
        assert config.output_directory == baseline.output_directory
        assert config.model.weights_path == Path(
            f"models/candidates/{candidate.candidate_id}/{candidate.weights_filename}"
        )
        assert config.model.source_url == candidate.source_url
        assert config.model.license_id == candidate.license_id
        assert config.model.license_url == candidate.license_url
        assert config.model.class_mapping.as_dict() == dict(candidate.class_mapping)


def test_candidate_confidence_sweeps_use_only_predeclared_values():
    baseline = load_evaluation_config(BASELINE_CONFIG)

    for path in SWEEP_CONFIGS.values():
        sweep = load_confidence_sweep_config(path)

        assert sweep.protocol_version == baseline.protocol_version
        assert sweep.operating_confidences == (0.10, 0.15, 0.25, 0.40, 0.50)
