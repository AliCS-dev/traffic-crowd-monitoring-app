from types import SimpleNamespace

from app.services.detection_service import extract_detection_records


def test_extract_detection_records_returns_database_ready_values():
    result = SimpleNamespace(
        names={0: "person", 2: "car"},
        boxes=[
            SimpleNamespace(
                cls=[2],
                conf=[0.91],
                xyxy=[[10.0, 20.0, 50.0, 80.0]],
            ),
            SimpleNamespace(
                cls=[0],
                conf=[0.75],
                xyxy=[[100.0, 120.0, 140.0, 180.0]],
            ),
        ],
    )

    detection_records = extract_detection_records(result)

    assert detection_records == [
        {
            "object_class": "car",
            "confidence": 0.91,
            "bbox_x_min": 10.0,
            "bbox_y_min": 20.0,
            "bbox_x_max": 50.0,
            "bbox_y_max": 80.0,
        },
        {
            "object_class": "person",
            "confidence": 0.75,
            "bbox_x_min": 100.0,
            "bbox_y_min": 120.0,
            "bbox_x_max": 140.0,
            "bbox_y_max": 180.0,
        },
    ]


def test_extract_detection_records_handles_empty_results():
    result = SimpleNamespace(names={}, boxes=[])

    assert extract_detection_records(result) == []
