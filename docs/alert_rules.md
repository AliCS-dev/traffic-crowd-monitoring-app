# Experimental Alert Rules

## Purpose

We use threshold rules to turn stored object counts into visible application
notifications. The evaluator is independent of YOLO: it receives ordinary class
counts and optional grid results, applies validated rules, and returns typed alert
records. This separation lets us test boundary behavior without loading a model.

An alert in this project has a deliberately narrow meaning. It says that a
model-produced count crossed a configured software threshold. It does not prove
traffic congestion, physical crowd density, danger, or an emergency.

## Current Configuration

The tracked configuration is `configs/runtime/alert_rules.json`. It is loaded and
validated when the application services are created. API requests cannot replace
the rule file or supply unrecorded thresholds.

| Rule ID | Class | Scope | Comparison | Threshold | Severity |
| --- | --- | --- | --- | ---: | --- |
| `frame-car-or-van-warning` | `car_or_van` | frame | greater than or equal | 20 | warning |
| `grid-person-information` | `person` | grid cell | greater than or equal | 8 | information |

These thresholds are illustrative application settings. They have not been
validated as traffic-management or public-safety limits. Any future change should
be committed with its rationale and tested before results are generated with it.

## Rule Fields

- `rule_id` is the stable identifier stored as the alert type.
- `analysis_method` is currently `detector_object_count` only.
- `object_class` selects one mapped project class.
- `scope` is either `frame` or `grid_cell`.
- `comparison` is `greater_than` or `greater_than_or_equal`.
- `threshold` is a positive integer because detector counts are discrete.
- `severity` is `information`, `warning`, or `critical` for interface display.

The severity is a presentation category. Even `critical` would not authorize an
operational response or imply that the application detected an emergency.

## Boundary And Missing-Count Behavior

`greater_than_or_equal` triggers when the measured count equals or exceeds the
threshold. `greater_than` triggers only above it. If the selected class is absent,
its measured count is zero. Empty grid cells therefore do not trigger any current
positive threshold. Grid rules are skipped when an analysis was run without a
grid because no grid-cell measurement exists.

Rules are evaluated in stable rule-ID order, and grid cells remain in row-major
order. Every generated record stores its measured count, threshold, severity,
comparison, frame ID, and optional grid-cell ID.

## Duplicate Protection

PostgreSQL permits one alert for each combination of processed frame, optional
grid cell, and rule ID. Alert insertion uses conflict-safe semantics, so applying
the same rule to the same stored result again does not add another row.

## Limitations

The alerts inherit every limitation of their source counts. The current detector
failed the final held-out quality gate and can miss or misclassify small aerial
objects. A count threshold also ignores road geometry, physical area, camera
calibration, traffic speed, duration, and local operating policy. We expose the
measured value and rule threshold so the interface and thesis can describe what
actually happened without making a stronger claim.
