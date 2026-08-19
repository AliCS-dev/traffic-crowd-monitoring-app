import json

import pytest
from pydantic import ValidationError

from app.crowd_analysis import (
    DenseCrowdDecisionError,
    load_dense_crowd_analysis_decision,
)
from app.schemas.monitoring import DenseCrowdAnalysisResult


def test_runtime_decision_matches_rejected_evaluation_evidence():
    decision = load_dense_crowd_analysis_decision()

    assert decision.status == "unsupported"
    assert decision.count is None
    assert decision.method_id is None
    assert decision.model_id is None
    assert decision.evaluated_candidate_id == "p2pnet-shtecha"
    assert decision.quality_gate_status == "failed"
    assert decision.reason_code == "no_accepted_dense_crowd_model"
    assert decision.evaluation_reference.as_posix() == (
        "docs/evaluation/dedicated_crowd_counting_result.md"
    )
    assert "held-out NAE exceeded" in decision.message


def test_non_rejected_evaluation_cannot_enter_the_rejection_path(tmp_path):
    result_path = tmp_path / "crowd-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate": {"candidate_id": "future-model"},
                "comparison": {
                    "decision": "integrate",
                    "decision_reason": "Future model passed.",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DenseCrowdDecisionError, match="recorded 'reject' decision"):
        load_dense_crowd_analysis_decision(result_path)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"schema_version": 2},
        {"schema_version": 1, "candidate": {}, "comparison": {}},
    ],
)
def test_incomplete_evaluation_evidence_is_rejected(tmp_path, values):
    result_path = tmp_path / "crowd-result.json"
    result_path.write_text(json.dumps(values), encoding="utf-8")

    with pytest.raises(DenseCrowdDecisionError):
        load_dense_crowd_analysis_decision(result_path)


def test_unsupported_api_result_cannot_report_a_false_zero():
    with pytest.raises(ValidationError, match="cannot contain a count"):
        DenseCrowdAnalysisResult(
            status="unsupported",
            count=0,
            method_id=None,
            model_id=None,
            evaluated_candidate_id="p2pnet-shtecha",
            quality_gate_status="failed",
            evaluation_reference=("docs/evaluation/dedicated_crowd_counting_result.md"),
            reason_code="no_accepted_dense_crowd_model",
            message="Rejected candidate",
        )
