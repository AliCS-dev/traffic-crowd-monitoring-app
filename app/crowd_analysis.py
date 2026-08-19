import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.config import (
    DENSE_CROWD_EVALUATION_PATH,
    DENSE_CROWD_EVALUATION_REFERENCE,
)


class DenseCrowdDecisionError(ValueError):
    """Raised when the recorded crowd-counting decision cannot be applied safely."""


@dataclass(frozen=True)
class DenseCrowdAnalysisDecision:
    status: Literal["unsupported"]
    count: None
    method_id: None
    model_id: None
    evaluated_candidate_id: str
    quality_gate_status: Literal["failed"]
    evaluation_reference: Path
    reason_code: str
    message: str


def load_dense_crowd_analysis_decision(
    path: Path = DENSE_CROWD_EVALUATION_PATH,
) -> DenseCrowdAnalysisDecision:
    path = Path(path)
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DenseCrowdDecisionError(
            f"Dense-crowd evaluation result not found: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise DenseCrowdDecisionError(
            f"Dense-crowd evaluation result is not valid JSON: {path}"
        ) from error

    root = _object(values, "evaluation result")
    if root.get("schema_version") != 1:
        raise DenseCrowdDecisionError(
            "Dense-crowd evaluation schema_version must be 1."
        )

    candidate = _object(root.get("candidate"), "candidate")
    comparison = _object(root.get("comparison"), "comparison")
    candidate_id = _non_empty_string(candidate.get("candidate_id"), "candidate_id")
    decision = _non_empty_string(comparison.get("decision"), "comparison.decision")
    reason = _non_empty_string(
        comparison.get("decision_reason"),
        "comparison.decision_reason",
    )

    if decision != "reject":
        raise DenseCrowdDecisionError(
            "The application rejection path requires a recorded 'reject' decision."
        )

    return DenseCrowdAnalysisDecision(
        status="unsupported",
        count=None,
        method_id=None,
        model_id=None,
        evaluated_candidate_id=candidate_id,
        quality_gate_status="failed",
        evaluation_reference=DENSE_CROWD_EVALUATION_REFERENCE,
        reason_code="no_accepted_dense_crowd_model",
        message=reason,
    )


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DenseCrowdDecisionError(f"{field} must be a JSON object.")
    return value


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DenseCrowdDecisionError(f"{field} must be a non-empty string.")
    return value.strip()
