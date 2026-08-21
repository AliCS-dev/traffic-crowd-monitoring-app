import json
from dataclasses import replace

import pytest

from app.services.alert_service import (
    AlertAnalysisMethod,
    AlertComparison,
    AlertRuleError,
    AlertScope,
    AlertSeverity,
    ThresholdAlertRule,
    evaluate_threshold_alerts,
    load_threshold_alert_rules,
)
from app.services.grid_counting_service import count_detections_by_grid


def rule(**overrides):
    values = {
        "rule_id": "frame-car-warning",
        "analysis_method": AlertAnalysisMethod.DETECTOR_OBJECT_COUNT,
        "object_class": "car_or_van",
        "scope": AlertScope.FRAME,
        "comparison": AlertComparison.GREATER_THAN_OR_EQUAL,
        "threshold": 2,
        "severity": AlertSeverity.WARNING,
    }
    values.update(overrides)
    return ThresholdAlertRule(**values)


def test_tracked_alert_rules_are_valid_and_deterministically_ordered():
    rules = load_threshold_alert_rules()

    assert [item.rule_id for item in rules] == [
        "frame-car-or-van-warning",
        "grid-person-information",
    ]
    assert rules[0].threshold == 20
    assert rules[1].scope is AlertScope.GRID_CELL
    assert rules[1].severity is AlertSeverity.INFORMATION


@pytest.mark.parametrize(
    ("count", "expected_alert_count"),
    [(1, 0), (2, 1), (3, 1)],
)
def test_greater_than_or_equal_rule_has_explicit_boundary(count, expected_alert_count):
    alerts = evaluate_threshold_alerts(
        [rule()],
        frame_object_counts={"car_or_van": count},
    )

    assert len(alerts) == expected_alert_count
    if alerts:
        assert alerts[0].measured_value == count
        assert alerts[0].threshold_value == 2
        assert "Experimental detector count" in alerts[0].message


def test_greater_than_rule_does_not_trigger_on_equality():
    strict_rule = replace(rule(), comparison=AlertComparison.GREATER_THAN)

    equal = evaluate_threshold_alerts(
        [strict_rule], frame_object_counts={"car_or_van": 2}
    )
    above = evaluate_threshold_alerts(
        [strict_rule], frame_object_counts={"car_or_van": 3}
    )

    assert equal == ()
    assert len(above) == 1
    assert "exceeded threshold" in above[0].message


def test_missing_class_and_empty_grid_cells_do_not_trigger_positive_thresholds():
    grid = count_detections_by_grid([], 100, 100, rows=2, columns=2)
    grid_rule = replace(
        rule(),
        rule_id="grid-person-warning",
        object_class="person",
        scope=AlertScope.GRID_CELL,
        threshold=1,
    )

    alerts = evaluate_threshold_alerts(
        [rule(), grid_rule],
        frame_object_counts={},
        grid_count_result=grid,
    )

    assert alerts == ()


def test_grid_alert_retains_cell_lineage_and_severity():
    detections = [
        {
            "object_class": "person",
            "bbox_x_min": 60,
            "bbox_y_min": 10,
            "bbox_x_max": 80,
            "bbox_y_max": 30,
        }
    ]
    grid = count_detections_by_grid(detections, 100, 100, rows=2, columns=2)
    grid_rule = replace(
        rule(),
        rule_id="grid-person-information",
        object_class="person",
        scope=AlertScope.GRID_CELL,
        threshold=1,
        severity=AlertSeverity.INFORMATION,
    )

    alerts = evaluate_threshold_alerts(
        [grid_rule],
        frame_object_counts={"person": 1},
        grid_count_result=grid,
    )

    assert len(alerts) == 1
    assert alerts[0].grid_row_index == 0
    assert alerts[0].grid_column_index == 1
    assert alerts[0].severity is AlertSeverity.INFORMATION
    assert "grid cell (0, 1)" in alerts[0].message


def test_rules_are_evaluated_in_rule_id_order():
    second = replace(rule(), rule_id="z-rule", threshold=1)
    first = replace(rule(), rule_id="a-rule", threshold=1)

    alerts = evaluate_threshold_alerts(
        [second, first],
        frame_object_counts={"car_or_van": 1},
    )

    assert [alert.rule_id for alert in alerts] == ["a-rule", "z-rule"]


def test_direct_rule_construction_and_duplicate_evaluation_are_validated():
    with pytest.raises(AlertRuleError, match="threshold must be an integer"):
        replace(rule(), threshold=0)

    duplicate = rule()
    with pytest.raises(AlertRuleError, match="unique before evaluation"):
        evaluate_threshold_alerts(
            [duplicate, duplicate],
            frame_object_counts={"car_or_van": 2},
        )


def write_rules(tmp_path, rules, **root_overrides):
    values = {"schema_version": 1, "rules": rules}
    values.update(root_overrides)
    path = tmp_path / "alert_rules.json"
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def valid_rule_values(**overrides):
    values = {
        "rule_id": "frame-car-warning",
        "analysis_method": "detector_object_count",
        "object_class": "car_or_van",
        "scope": "frame",
        "comparison": "greater_than_or_equal",
        "threshold": 2,
        "severity": "warning",
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    ("rules", "message"),
    [
        ([], "non-empty list"),
        ([valid_rule_values(threshold=0)], "integer >= 1"),
        ([valid_rule_values(scope="area")], "unsupported option"),
        ([valid_rule_values(severity="emergency")], "unsupported option"),
        ([valid_rule_values(object_class="train")], "not a project class"),
        ([valid_rule_values(unexpected=True)], "unknown fields"),
        (
            [valid_rule_values(), valid_rule_values()],
            "rule_id values must be unique",
        ),
    ],
)
def test_invalid_rule_configuration_is_rejected(tmp_path, rules, message):
    with pytest.raises(AlertRuleError, match=message):
        load_threshold_alert_rules(write_rules(tmp_path, rules))


@pytest.mark.parametrize("counts", [{"person": -1}, {"person": 1.5}, {"": 1}])
def test_invalid_count_inputs_are_rejected(counts):
    with pytest.raises(AlertRuleError):
        evaluate_threshold_alerts([rule()], frame_object_counts=counts)
