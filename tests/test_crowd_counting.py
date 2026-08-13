import json
from pathlib import Path

import pytest
from PIL import Image

from evaluation.crowd_counting import (
    CrowdCountingError,
    CrowdCountObservation,
    bootstrap_count_intervals,
    calculate_count_metrics,
    classify_candidate,
    load_crowd_counting_config,
    parse_crowd_counting_config,
    runtime_summary,
)
from evaluation.p2pnet_adapter import iter_image_tiles

CONFIG_PATH = Path("configs/evaluation/dedicated_crowd_counting.json")


def load_values():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def observations():
    return (
        CrowdCountObservation("one", 100, 80, 1000, 1000, 0.2, 1),
        CrowdCountObservation("two", 50, 70, 2000, 1000, 0.6, 2),
    )


def test_tracked_crowd_counting_protocol_is_valid_and_frozen():
    config = load_crowd_counting_config(CONFIG_PATH)

    assert config.candidate.candidate_id == "p2pnet-shtecha"
    assert config.candidate.repository_revision == (
        "5c91a81ca062b1c7fd3db3ad1c55b1c21f0a7455"
    )
    assert config.inference.operating_confidence == 0.5
    assert config.inference.tile_overlap == 0
    assert config.inference.edge_tile_policy.startswith("pad-right-bottom")
    assert config.dataset.expected_final_images == 14


def test_config_rejects_unknown_fields():
    values = load_values()
    values["candidate"]["unreviewed_setting"] = True

    with pytest.raises(CrowdCountingError, match="unknown fields"):
        parse_crowd_counting_config(values)


def test_config_rejects_overlapping_tiles():
    values = load_values()
    values["inference"]["tile_overlap"] = 128

    with pytest.raises(CrowdCountingError, match="no overlap"):
        parse_crowd_counting_config(values)


def test_tiles_cover_the_image_once_and_preserve_edge_dimensions():
    image = Image.new("RGB", (2500, 1300))

    tiles = list(iter_image_tiles(image, 1024))

    assert [tile.size for tile in tiles] == [
        (1024, 1024),
        (1024, 1024),
        (452, 1024),
        (1024, 276),
        (1024, 276),
        (452, 276),
    ]
    assert sum(width * height for width, height in (tile.size for tile in tiles)) == (
        2500 * 1300
    )


def test_count_metrics_and_runtime_use_complete_images():
    metrics = calculate_count_metrics(observations())
    runtime = runtime_summary(observations(), 64 * 1024 * 1024)

    assert metrics["ground_truth_total"] == 150
    assert metrics["predicted_total"] == 150
    assert metrics["mean_absolute_error"] == 20
    assert metrics["root_mean_squared_error"] == 20
    assert metrics["normalized_absolute_error"] == pytest.approx(40 / 150)
    assert metrics["bias"] == 0
    assert runtime["median_seconds_per_image"] == pytest.approx(0.4)
    assert runtime["median_seconds_per_megapixel"] == pytest.approx(0.25)
    assert runtime["peak_allocated_gpu_memory_mib"] == 64


def test_bootstrap_intervals_are_reproducible():
    first = bootstrap_count_intervals(observations(), iterations=100, seed=2026)
    second = bootstrap_count_intervals(observations(), iterations=100, seed=2026)

    assert first == second
    assert first["normalized_absolute_error"]["lower_95"] >= 0


def test_decision_rules_are_applied_in_order():
    settings = load_crowd_counting_config(CONFIG_PATH).decision

    assert classify_candidate(0.30, 0.99, 0.2, settings)["decision"] == "integrate"
    assert classify_candidate(0.60, 0.99, 0.7, settings)["decision"] == "defer"
    assert classify_candidate(0.90, 0.99, 0.2, settings)["decision"] == "reject"
