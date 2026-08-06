import json
from copy import deepcopy
from pathlib import Path

import pytest

from evaluation.evaluation_config import PROJECT_CLASSES
from evaluation.model_candidates import (
    ModelCandidateError,
    load_model_candidate_selection,
    parse_model_candidate_selection,
)

CONFIG_PATH = Path("configs/evaluation/aerial_model_candidates.json")


def load_values() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_tracked_aerial_candidate_selection_is_valid_and_limited():
    selection = load_model_candidate_selection(CONFIG_PATH)

    assert selection.dataset_role == "validation"
    assert selection.maximum_candidates == 3
    assert tuple(candidate.candidate_id for candidate in selection.candidates) == (
        "yolo26m-visdrone",
        "yolo11x-visdrone",
    )
    assert len(selection.candidates) == 2


def test_candidates_cover_the_operational_taxonomy_and_pin_weights():
    selection = load_model_candidate_selection(CONFIG_PATH)

    for candidate in selection.candidates:
        mapped_classes = {project_class for _, project_class in candidate.class_mapping}
        declared_source_classes = {
            source_class for source_class, _ in candidate.class_mapping
        } | set(candidate.excluded_source_classes)
        assert mapped_classes == set(PROJECT_CLASSES)
        assert declared_source_classes == set(candidate.source_classes)
        assert candidate.source_classes[-1] == "others"
        assert candidate.repository_revision in candidate.weights_url
        assert candidate.weights_url.endswith(f"/{candidate.weights_filename}")
        assert len(candidate.weights_sha256) == 64


def test_candidate_limit_is_enforced():
    values = load_values()
    values["candidates"].extend(deepcopy(values["candidates"]))

    with pytest.raises(ModelCandidateError, match="no more than 3"):
        parse_model_candidate_selection(values)


def test_held_out_role_is_rejected():
    values = load_values()
    values["dataset_role"] = "held_out_test"

    with pytest.raises(ModelCandidateError, match="must be validation"):
        parse_model_candidate_selection(values)


def test_incomplete_class_mapping_is_rejected():
    values = load_values()
    del values["candidates"][0]["class_mapping"]["bus"]

    with pytest.raises(ModelCandidateError, match="does not cover project classes"):
        parse_model_candidate_selection(values)


def test_unpinned_weight_url_is_rejected():
    values = load_values()
    values["candidates"][0]["weights_url"] = (
        "https://huggingface.co/dronefreak/visdrone-yolov26m/resolve/main/best.pt"
    )

    with pytest.raises(ModelCandidateError, match="must pin"):
        parse_model_candidate_selection(values)


def test_unknown_candidate_field_is_rejected():
    values = load_values()
    values["candidates"][0]["unreviewed_option"] = True

    with pytest.raises(ModelCandidateError, match="unknown fields"):
        parse_model_candidate_selection(values)


def test_source_classes_must_match_mapping_and_exclusions():
    values = load_values()
    values["candidates"][0]["source_classes"].remove("others")

    with pytest.raises(ModelCandidateError, match="mapped and excluded"):
        parse_model_candidate_selection(values)
