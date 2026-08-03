import csv
from pathlib import Path

import pytest

from evaluation.dataset_selection import (
    apply_exclusions,
    exclusion_ids,
    uniform_indices,
    validate_selection_plan,
)

PLAN_PATH = Path("data/evaluation/selection_plan.csv")
EXCLUSIONS_PATH = Path("data/evaluation/exclusions.csv")


def read_plan() -> list[dict[str, str]]:
    with PLAN_PATH.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def test_uniform_indices_cover_sequence_without_duplicates():
    indices = uniform_indices(total=100, count=5)

    assert indices == [10, 30, 50, 70, 90]
    assert len(indices) == len(set(indices))


def test_uniform_indices_reject_invalid_sample_size():
    with pytest.raises(ValueError, match="Cannot select"):
        uniform_indices(total=3, count=4)


def test_selection_plan_is_leakage_safe_and_has_expected_candidate_size():
    rows = read_plan()

    validate_selection_plan(rows)

    assert sum(int(row["sample_count"]) for row in rows) == 350
    assert {row["dataset_role"] for row in rows} == {
        "training",
        "validation",
        "held_out_test",
    }


def test_incomplete_manual_frames_are_explicitly_excluded():
    excluded = exclusion_ids(EXCLUSIONS_PATH)

    assert excluded == {
        "wikimedia_jane_byrne_f000609",
        "wikimedia_jane_byrne_f000702",
        "wikimedia_jane_byrne_f000796",
        "wikimedia_jane_byrne_f000890",
    }

    records = [{"asset_id": asset_id} for asset_id in sorted(excluded | {"retained"})]
    assert apply_exclusions(records, excluded) == [{"asset_id": "retained"}]


def test_exclusions_must_reference_generated_assets():
    with pytest.raises(ValueError, match="unknown assets"):
        apply_exclusions([{"asset_id": "retained"}], {"unknown"})


def test_published_test_sources_remain_held_out():
    rows = read_plan()
    published_test_rows = [
        row for row in rows if row["source_split"] == "published_test"
    ]

    assert published_test_rows
    assert {row["dataset_role"] for row in published_test_rows} == {"held_out_test"}
