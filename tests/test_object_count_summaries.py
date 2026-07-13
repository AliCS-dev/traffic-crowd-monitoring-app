from app.services.detection_service import build_object_count_summary_records


def test_build_object_count_summary_records_returns_sorted_database_ready_values():
    object_counts = {
        "person": 3,
        "car": 5,
    }

    summary_records = build_object_count_summary_records(object_counts)

    assert summary_records == [
        {
            "object_class": "car",
            "object_count": 5,
        },
        {
            "object_class": "person",
            "object_count": 3,
        },
    ]


def test_build_object_count_summary_records_handles_empty_counts():
    assert build_object_count_summary_records({}) == []
