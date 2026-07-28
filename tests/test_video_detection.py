from types import SimpleNamespace

import numpy as np
import pytest

import app.services.detection_service as detection_service
from app.services.detection_service import ObjectDetector
from app.services.frame_sampling_service import SampledFrame
from app.services.video_detection_service import process_sampled_video_frames


class FakeDetector:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def detect(self, image, confidence_threshold, image_size):
        self.calls.append(
            {
                "image": image,
                "confidence_threshold": confidence_threshold,
                "image_size": image_size,
            }
        )
        return self.results


def create_detection_result():
    return SimpleNamespace(
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


def test_object_detector_loads_model_once_and_reuses_it(monkeypatch):
    model_calls = []

    class FakeModel:
        def __call__(self, image, conf, imgsz):
            model_calls.append(
                {
                    "image": image,
                    "confidence_threshold": conf,
                    "image_size": imgsz,
                }
            )
            return ["result"]

    loaded_model_paths = []

    def create_fake_model(model_path):
        loaded_model_paths.append(model_path)
        return FakeModel()

    monkeypatch.setattr(detection_service, "YOLO", create_fake_model)
    detector = ObjectDetector("models/test-model.pt")
    first_image = np.zeros((2, 2, 3), dtype=np.uint8)
    second_image = np.ones((2, 2, 3), dtype=np.uint8)

    first_result = detector.detect(
        first_image, confidence_threshold=0.2, image_size=640
    )
    second_result = detector.detect(
        second_image,
        confidence_threshold=0.3,
        image_size=1280,
    )

    assert loaded_model_paths == ["models/test-model.pt"]
    assert first_result == ["result"]
    assert second_result == ["result"]
    assert model_calls == [
        {
            "image": first_image,
            "confidence_threshold": 0.2,
            "image_size": 640,
        },
        {
            "image": second_image,
            "confidence_threshold": 0.3,
            "image_size": 1280,
        },
    ]


def test_sampled_frames_are_processed_with_metadata_and_counts():
    first_image = np.zeros((2, 3, 3), dtype=np.uint8)
    second_image = np.ones((2, 3, 3), dtype=np.uint8)
    sampled_frames = [
        SampledFrame(frame_number=0, timestamp_seconds=0, image=first_image),
        SampledFrame(frame_number=30, timestamp_seconds=1, image=second_image),
    ]
    detector = FakeDetector([create_detection_result()])

    processed_frames = list(
        process_sampled_video_frames(
            sampled_frames,
            detector,
            confidence_threshold=0.25,
            image_size=640,
            scale_factor=2,
        )
    )

    assert len(processed_frames) == 2
    assert [frame.frame_number for frame in processed_frames] == [0, 30]
    assert [frame.timestamp_seconds for frame in processed_frames] == [0, 1]
    assert [(frame.image_width, frame.image_height) for frame in processed_frames] == [
        (6, 4),
        (6, 4),
    ]
    assert processed_frames[0].object_counts == {"car": 1, "person": 1}
    assert processed_frames[0].detection_records == [
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
    assert len(detector.calls) == 2
    assert detector.calls[0]["image"].shape == (4, 6, 3)
    assert detector.calls[0]["confidence_threshold"] == 0.25
    assert detector.calls[0]["image_size"] == 640


def test_empty_sample_sequence_produces_no_results():
    detector = FakeDetector([create_detection_result()])

    processed_frames = list(process_sampled_video_frames([], detector))

    assert processed_frames == []
    assert detector.calls == []


def test_frame_with_no_detections_still_produces_result():
    sampled_frame = SampledFrame(
        frame_number=30,
        timestamp_seconds=1,
        image=np.zeros((2, 2, 3), dtype=np.uint8),
    )
    detector = FakeDetector([SimpleNamespace(names={}, boxes=[])])

    processed_frames = list(process_sampled_video_frames([sampled_frame], detector))

    assert len(processed_frames) == 1
    assert processed_frames[0].frame_number == 30
    assert processed_frames[0].detection_records == []
    assert processed_frames[0].object_counts == {}


def test_missing_model_result_identifies_frame():
    sampled_frame = SampledFrame(
        frame_number=60,
        timestamp_seconds=2,
        image=np.zeros((2, 2, 3), dtype=np.uint8),
    )
    detector = FakeDetector([])

    with pytest.raises(ValueError, match="frame 60"):
        list(process_sampled_video_frames([sampled_frame], detector))
