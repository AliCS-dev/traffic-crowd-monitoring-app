import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from app.config import ALERT_RULES_PATH
from app.model_profile import PROJECT_CLASSES
from app.services.grid_counting_service import GridCountResult

RULE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OBJECT_CLASS_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class AlertRuleError(ValueError):
    """Raised when threshold-alert configuration is incomplete or invalid."""


class AlertAnalysisMethod(str, Enum):
    DETECTOR_OBJECT_COUNT = "detector_object_count"


class AlertScope(str, Enum):
    FRAME = "frame"
    GRID_CELL = "grid_cell"


class AlertComparison(str, Enum):
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"


class AlertSeverity(str, Enum):
    INFORMATION = "information"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ThresholdAlertRule:
    rule_id: str
    analysis_method: AlertAnalysisMethod
    object_class: str
    scope: AlertScope
    comparison: AlertComparison
    threshold: int
    severity: AlertSeverity

    def __post_init__(self) -> None:
        _identifier(self.rule_id, "rule_id", RULE_ID_PATTERN)
        _identifier(self.object_class, "object_class", OBJECT_CLASS_PATTERN)
        if self.object_class not in PROJECT_CLASSES:
            raise AlertRuleError("object_class is not a project class.")
        for field, value, enum_type in (
            ("analysis_method", self.analysis_method, AlertAnalysisMethod),
            ("scope", self.scope, AlertScope),
            ("comparison", self.comparison, AlertComparison),
            ("severity", self.severity, AlertSeverity),
        ):
            if not isinstance(value, enum_type):
                raise AlertRuleError(f"{field} contains an unsupported option.")
        _integer(self.threshold, "threshold", minimum=1)


@dataclass(frozen=True)
class ThresholdAlert:
    rule_id: str
    analysis_method: AlertAnalysisMethod
    object_class: str
    scope: AlertScope
    comparison: AlertComparison
    severity: AlertSeverity
    message: str
    measured_value: int
    threshold_value: int
    grid_row_index: int | None = None
    grid_column_index: int | None = None


def load_threshold_alert_rules(
    path: Path = ALERT_RULES_PATH,
) -> tuple[ThresholdAlertRule, ...]:
    path = Path(path)
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AlertRuleError(f"Alert-rule configuration not found: {path}") from error
    except json.JSONDecodeError as error:
        raise AlertRuleError(
            f"Alert-rule configuration is not valid JSON: {path}"
        ) from error

    root = _object(values, "configuration")
    _fields(root, "configuration", {"schema_version", "rules"})
    if _integer(root["schema_version"], "schema_version", minimum=1) != 1:
        raise AlertRuleError("schema_version must be 1.")
    if not isinstance(root["rules"], list) or not root["rules"]:
        raise AlertRuleError("rules must be a non-empty list.")

    rules = tuple(
        _build_rule(value, index) for index, value in enumerate(root["rules"])
    )
    rule_ids = [rule.rule_id for rule in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise AlertRuleError("rule_id values must be unique.")
    return tuple(sorted(rules, key=lambda rule: rule.rule_id))


def evaluate_threshold_alerts(
    rules: Sequence[ThresholdAlertRule],
    *,
    frame_object_counts: Mapping[str, int],
    grid_count_result: GridCountResult | None = None,
) -> tuple[ThresholdAlert, ...]:
    rule_ids = [rule.rule_id for rule in rules]
    if len(rule_ids) != len(set(rule_ids)):
        raise AlertRuleError("rule_id values must be unique before evaluation.")
    _validate_object_counts(frame_object_counts, "frame_object_counts")
    alerts = []

    for rule in sorted(rules, key=lambda item: item.rule_id):
        if rule.analysis_method is not AlertAnalysisMethod.DETECTOR_OBJECT_COUNT:
            raise AlertRuleError(
                f"Unsupported alert analysis method: {rule.analysis_method.value}."
            )

        if rule.scope is AlertScope.FRAME:
            measured_value = frame_object_counts.get(rule.object_class, 0)
            if _threshold_crossed(measured_value, rule):
                alerts.append(_build_alert(rule, measured_value))
            continue

        if grid_count_result is None:
            continue
        for cell in grid_count_result.cells:
            measured_value = cell.object_counts.get(rule.object_class, 0)
            if _threshold_crossed(measured_value, rule):
                alerts.append(
                    _build_alert(
                        rule,
                        measured_value,
                        grid_row_index=cell.row_index,
                        grid_column_index=cell.column_index,
                    )
                )

    return tuple(alerts)


def _build_rule(value: Any, index: int) -> ThresholdAlertRule:
    field = f"rules[{index}]"
    values = _object(value, field)
    _fields(
        values,
        field,
        {
            "rule_id",
            "analysis_method",
            "object_class",
            "scope",
            "comparison",
            "threshold",
            "severity",
        },
    )
    rule_id = _identifier(values["rule_id"], f"{field}.rule_id", RULE_ID_PATTERN)
    object_class = _identifier(
        values["object_class"],
        f"{field}.object_class",
        OBJECT_CLASS_PATTERN,
    )
    if object_class not in PROJECT_CLASSES:
        raise AlertRuleError(f"{field}.object_class is not a project class.")
    try:
        analysis_method = AlertAnalysisMethod(values["analysis_method"])
        scope = AlertScope(values["scope"])
        comparison = AlertComparison(values["comparison"])
        severity = AlertSeverity(values["severity"])
    except (TypeError, ValueError) as error:
        raise AlertRuleError(f"{field} contains an unsupported option.") from error

    return ThresholdAlertRule(
        rule_id=rule_id,
        analysis_method=analysis_method,
        object_class=object_class,
        scope=scope,
        comparison=comparison,
        threshold=_integer(values["threshold"], f"{field}.threshold", minimum=1),
        severity=severity,
    )


def _build_alert(
    rule: ThresholdAlertRule,
    measured_value: int,
    *,
    grid_row_index: int | None = None,
    grid_column_index: int | None = None,
) -> ThresholdAlert:
    if rule.scope is AlertScope.FRAME:
        location = "the processed frame"
    else:
        location = f"grid cell ({grid_row_index}, {grid_column_index})"
    boundary = (
        "exceeded"
        if rule.comparison is AlertComparison.GREATER_THAN
        else "met or exceeded"
    )
    message = (
        f"Experimental detector count for '{rule.object_class}' in {location} "
        f"{boundary} threshold {rule.threshold} (measured {measured_value})."
    )
    return ThresholdAlert(
        rule_id=rule.rule_id,
        analysis_method=rule.analysis_method,
        object_class=rule.object_class,
        scope=rule.scope,
        comparison=rule.comparison,
        severity=rule.severity,
        message=message,
        measured_value=measured_value,
        threshold_value=rule.threshold,
        grid_row_index=grid_row_index,
        grid_column_index=grid_column_index,
    )


def _threshold_crossed(measured_value: int, rule: ThresholdAlertRule) -> bool:
    if rule.comparison is AlertComparison.GREATER_THAN:
        return measured_value > rule.threshold
    return measured_value >= rule.threshold


def _validate_object_counts(values: Mapping[str, int], field: str) -> None:
    if not isinstance(values, Mapping):
        raise AlertRuleError(f"{field} must be a mapping.")
    for object_class, count in values.items():
        if not isinstance(object_class, str) or not object_class.strip():
            raise AlertRuleError(f"{field} contains an invalid object class.")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise AlertRuleError(f"{field} counts must be non-negative integers.")


def _fields(values: dict[str, Any], field: str, required: set[str]) -> None:
    missing = required - set(values)
    unknown = set(values) - required
    if missing:
        raise AlertRuleError(
            f"{field} is missing required fields: {', '.join(sorted(missing))}."
        )
    if unknown:
        raise AlertRuleError(
            f"{field} contains unknown fields: {', '.join(sorted(unknown))}."
        )


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AlertRuleError(f"{field} must be a JSON object.")
    return value


def _identifier(value: Any, field: str, pattern: re.Pattern) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise AlertRuleError(f"{field} has an invalid identifier.")
    if len(value) > 100:
        raise AlertRuleError(f"{field} must contain at most 100 characters.")
    return value


def _integer(value: Any, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AlertRuleError(f"{field} must be an integer >= {minimum}.")
    return value
