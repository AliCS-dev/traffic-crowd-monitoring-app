"""Inspect the saved UAVDT baseline without inference or annotation changes."""

import argparse
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from evaluation.confidence_sweep import (
    load_source_evaluation_run,
    verify_source_dataset_identity,
)
from evaluation.error_analysis import (
    ErrorAnalysisConfig,
    create_error_analysis_result,
    save_error_analysis,
    select_representative_errors,
)
from evaluation.evaluation_data import load_evaluation_dataset
from evaluation.evaluation_metrics import filter_ignored_predictions
from evaluation.uavdt_media_check import render_overlay
from evaluation.uavdt_readiness import file_sha256, validate_uavdt_evaluation

BASELINE_RECORD = Path("data/evaluation/uavdt_daytime_baseline.json")
OUTPUT_DIRECTORY = Path("data/evaluation/derived/uavdt_error_review")
CATEGORY_IDS = {"car_or_van": 4, "truck": 5, "bus": 6}


def prediction_inventory(dataset, predictions, *, confidence, max_detections):
    """Count saved candidates separately from the scored operating predictions."""
    retained = filter_ignored_predictions(dataset, predictions)
    assets = dataset.asset_by_id()
    raw_by_asset = {asset.asset_id: [] for asset in dataset.assets}
    for prediction in predictions:
        raw_by_asset[prediction.asset_id].append(prediction)
    reference = Counter(
        (box.asset_id, box.project_class) for box in dataset.ground_truth_boxes
    )
    operating = Counter(
        (prediction.asset_id, prediction.project_class)
        for prediction in retained
        if prediction.confidence >= confidence
        and assets[prediction.asset_id].includes_class(prediction.project_class)
    )
    images = []
    for asset in dataset.assets:
        raw = raw_by_asset[asset.asset_id]
        images.append(
            {
                "asset_id": asset.asset_id,
                "sequence": asset.source_group_id,
                "raw_predictions": len(raw),
                "at_candidate_cap": len(raw) == max_detections,
                "lowest_saved_confidence": min(
                    (p.confidence for p in raw), default=None
                ),
                "reference": {
                    name: reference[asset.asset_id, name] for name in CATEGORY_IDS
                },
                "predicted": {
                    name: operating[asset.asset_id, name] for name in CATEGORY_IDS
                },
            }
        )
    capped = [image for image in images if image["at_candidate_cap"]]
    tails = [image["lowest_saved_confidence"] for image in capped]
    return {
        "images": images,
        "raw_predictions": len(predictions),
        "ignored_predictions_at_floor": len(predictions) - len(retained),
        "operating_target_predictions": sum(operating.values()),
        "images_at_candidate_cap": len(capped),
        "capped_tail_min": min(tails, default=None),
        "capped_tail_max": max(tails, default=None),
        "capped_images_with_tail_at_or_above_operating_confidence": sum(
            value >= confidence for value in tails
        ),
    }


def select_bus_truck_errors(detection):
    """Reuse the existing size/scene-diverse selection, three per type and class."""
    selected = {}
    for name in ("bus", "truck"):
        focused = replace(
            detection,
            errors=tuple(
                error
                for error in detection.errors
                if name in (error.expected_class, error.predicted_class)
            ),
        )
        for error in select_representative_errors(focused, 3):
            selected[error.error_id] = error
    return tuple(selected[key] for key in sorted(selected))


def render_sequence_comparisons(dataset, predictions, output, *, confidence):
    retained = filter_ignored_predictions(dataset, predictions)
    paths = []
    for asset in dataset.assets:
        if asset.source_group_id != "M0207":
            continue
        image = cv2.imread(str(asset.image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Unreadable review image: {asset.asset_id}")
        regions = [
            {"bbox": region.box.as_xywh()}
            for region in dataset.ignored_regions
            if region.asset_id == asset.asset_id
        ]
        reference = [
            {"bbox": box.box.as_xywh(), "category_id": CATEGORY_IDS[box.project_class]}
            for box in dataset.ground_truth_boxes
            if box.asset_id == asset.asset_id
        ]
        predicted = [
            {
                "bbox": prediction.box.as_xywh(),
                "category_id": CATEGORY_IDS[prediction.project_class],
            }
            for prediction in retained
            if prediction.asset_id == asset.asset_id
            and prediction.confidence >= confidence
            and asset.includes_class(prediction.project_class)
        ]
        panels = []
        for title, boxes in (
            ("Native labels", reference),
            ("Scored predictions", predicted),
        ):
            panel = render_overlay(image, boxes, regions)
            header = np.full((40, panel.shape[1], 3), 245, dtype=np.uint8)
            cv2.putText(
                header,
                f"{asset.asset_id} | {title}: {len(boxes)}",
                (10, 27),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (20, 20, 20),
                1,
            )
            panels.append(np.vstack((header, panel)))
        relative = Path("m0207") / f"{asset.asset_id}.png"
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(destination), np.hstack(panels)):
            raise ValueError(f"Could not write comparison: {destination}")
        paths.append(relative.as_posix())
    return paths


def review_saved_baseline(root: Path) -> Path:
    root = root.resolve()
    baseline = json.loads((root / BASELINE_RECORD).read_text(encoding="utf-8"))
    relative = Path(baseline["source_run_directory"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Baseline run must be repository-relative")
    source = load_source_evaluation_run(root / relative)
    if (
        source.run_id != baseline["source_run_id"]
        or source.manifest_sha256 != baseline["source_manifest_sha256"]
    ):
        raise ValueError("Saved run does not match the tracked baseline")
    verify_source_dataset_identity(root, source)
    readiness = validate_uavdt_evaluation(root, source.config)
    if readiness != baseline["provenance"]["source_evaluation_readiness"]:
        raise ValueError("Readiness differs from the completed baseline")
    dataset = load_evaluation_dataset(root, source.config.dataset)
    config = ErrorAnalysisConfig(
        schema_version=1,
        analysis_name="uavdt-saved-prediction-review",
        protocol_version=source.config.protocol_version,
        dataset_role="validation",
        operating_confidence=source.config.inference.operating_confidence,
        operating_iou=source.config.metrics.operating_iou,
        cases_per_error_type=3,
        count_error_cases=1,
        crop_size=640,
        context_multiplier=3.0,
        output_directory=OUTPUT_DIRECTORY,
    )
    result = create_error_analysis_result(dataset, source, config)
    totals = baseline["metrics"]["detection"]["per_class"]
    for field in ("true_positives", "false_positives", "false_negatives"):
        if getattr(result.detection, field) != sum(row[field] for row in totals):
            raise ValueError("Error totals differ from the recorded baseline")
    selected = select_bus_truck_errors(result.detection)
    result = replace(
        result, selected_detection_error_ids=tuple(error.error_id for error in selected)
    )
    saved = save_error_analysis(root, config, result, dataset, source)
    predictions = list(source.predictions.predictions)
    inventory = prediction_inventory(
        dataset,
        predictions,
        confidence=config.operating_confidence,
        max_detections=source.config.inference.max_detections,
    )
    comparisons = render_sequence_comparisons(
        dataset,
        predictions,
        saved.output_directory,
        confidence=config.operating_confidence,
    )
    confusion = Counter(
        f"{error.expected_class}->{error.predicted_class}"
        for error in result.detection.errors
        if error.error_type in ("class_confusion", "excluded_label_confusion")
    )
    report = {
        "schema_version": 1,
        "record_type": "saved_prediction_diagnostics_not_new_accuracy",
        "source_run_id": source.run_id,
        "source_manifest_sha256": source.manifest_sha256,
        "baseline_record_sha256": file_sha256(root / BASELINE_RECORD),
        "analysis_id": saved.analysis_id,
        "analysis_directory": saved.output_directory.relative_to(root).as_posix(),
        "operating_confidence": config.operating_confidence,
        "operating_iou": config.operating_iou,
        "inventory": inventory,
        "matching_totals": {
            field: getattr(result.detection, field)
            for field in ("true_positives", "false_positives", "false_negatives")
        },
        "error_types": dict(
            Counter(error.error_type for error in result.detection.errors)
        ),
        "paired_class_disagreements": dict(sorted(confusion.items())),
        "selected_error_ids": list(result.selected_detection_error_ids),
        "selection_rule": (
            "all ten M0207 frames; existing size/scene-diverse selector, "
            "up to three errors per type for each of bus and truck; deduplicate IDs"
        ),
        "sequence_comparisons": comparisons,
        "new_inference_run": False,
        "annotations_changed": False,
        "human_annotation_review": False,
    }
    (saved.output_directory / "review.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    artifacts = [
        {
            "path": path.relative_to(saved.output_directory).as_posix(),
            "sha256": file_sha256(path),
        }
        for path in sorted(saved.output_directory.rglob("*"))
        if path.is_file()
    ]
    (saved.output_directory / "review_manifest.json").write_text(
        json.dumps({"artifacts": artifacts}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return saved.output_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    output = review_saved_baseline(Path(__file__).resolve().parents[1])
    print(f"Saved prediction review: {output}")


if __name__ == "__main__":
    main()
