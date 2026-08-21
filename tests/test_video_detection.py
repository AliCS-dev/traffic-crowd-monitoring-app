import hashlib
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

import app.services.detection_service as detection_service
from app.model_profile import load_runtime_model_profile
from app.services.detection_service import ObjectDetector
from app.services.frame_sampling_service import SampledFrame
from app.services.video_detection_service import process_sampled_video_frames

MODEL_PROFILE = load_runtime_model_profile()


class FakeDetector:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def detect(
        self,
        image,
        *,
        confidence_threshold,
        image_size,
        device,
        max_detections,
        half_precision,
    ):
        self.calls.append(
            {
                "image": image,
                "confidence_threshold": confidence_threshold,
                "image_size": image_size,
                "device": device,
                "max_detections": max_detections,
                "half_precision": half_precision,
            }
        )
        annotated_image = image.copy()
        for result in self.results:
            result.plot = lambda image=annotated_image: image
        return self.results


def create_detection_result():
    return SimpleNamespace(
        names={0: "pedestrian", 2: "car", 10: "others"},
        boxes=[
            SimpleNamespace(
                cls=[2],
                conf=[0.91],
                xyxy=[[1.0, 1.0, 3.0, 3.0]],
            ),
            SimpleNamespace(
                cls=[0],
                conf=[0.75],
                xyxy=[[3.0, 1.0, 5.0, 4.0]],
            ),
            SimpleNamespace(
                cls=[10],
                conf=[0.99],
                xyxy=[[0.0, 0.0, 1.0, 1.0]],
            ),
        ],
    )


def test_object_detector_loads_model_once_and_reuses_it(monkeypatch):
    model_calls = []

    class FakeModel:
        def __call__(self, image, conf, imgsz, max_det):
            model_calls.append(
                {
                    "image": image,
                    "confidence_threshold": conf,
                    "image_size": imgsz,
                    "max_detections": max_det,
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
        first_image,
        confidence_threshold=0.2,
        image_size=640,
        max_detections=300,
    )
    second_result = detector.detect(
        second_image,
        confidence_threshold=0.3,
        image_size=1280,
        max_detections=300,
    )

    assert loaded_model_paths == ["models/test-model.pt"]
    assert first_result == ["result"]
    assert second_result == ["result"]
    assert model_calls == [
        {
            "image": first_image,
            "confidence_threshold": 0.2,
            "image_size": 640,
            "max_detections": 300,
        },
        {
            "image": second_image,
            "confidence_threshold": 0.3,
            "image_size": 1280,
            "max_detections": 300,
        },
    ]


def test_object_detector_forwards_explicit_evaluation_options(monkeypatch):
    calls = []

    class FakeModel:
        def __call__(self, image, **options):
            calls.append((image, options))
            return ["result"]

    monkeypatch.setattr(detection_service, "YOLO", lambda _path: FakeModel())
    detector = ObjectDetector("models/test-model.pt")
    image = np.zeros((2, 2, 3), dtype=np.uint8)

    result = detector.detect(
        image,
        confidence_threshold=0.001,
        image_size=1280,
        device="cuda:0",
        max_detections=300,
        half_precision=True,
        verbose=False,
    )

    assert result == ["result"]
    assert calls == [
        (
            image,
            {
                "conf": 0.001,
                "imgsz": 1280,
                "device": "cuda:0",
                "max_det": 300,
                "half": True,
                "verbose": False,
            },
        )
    ]


def test_runtime_detector_verifies_checkpoint_before_loading_model(tmp_path):
    checkpoint = tmp_path / "model.pt"
    content = b"known model weights"
    checkpoint.write_bytes(content)
    profile = replace(
        MODEL_PROFILE,
        checkpoint_path=checkpoint.relative_to(tmp_path),
        checkpoint_size_bytes=len(content),
        checkpoint_sha256=hashlib.sha256(content).hexdigest(),
    )
    loaded_paths = []

    detector = ObjectDetector.from_runtime_profile(
        profile,
        repository_root=tmp_path,
        model_factory=lambda path: loaded_paths.append(path) or object(),
    )

    assert isinstance(detector, ObjectDetector)
    assert loaded_paths == [str(checkpoint)]


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
            replace(MODEL_PROFILE, image_size=640),
        )
    )

    assert len(processed_frames) == 2
    assert [frame.frame_number for frame in processed_frames] == [0, 30]
    assert [frame.timestamp_seconds for frame in processed_frames] == [0, 1]
    assert [(frame.image_width, frame.image_height) for frame in processed_frames] == [
        (6, 4),
        (6, 4),
    ]
    assert processed_frames[0].object_counts == {"car_or_van": 1, "person": 1}
    assert processed_frames[0].detection_records == [
        {
            "object_class": "car_or_van",
            "confidence": 0.91,
            "bbox_x_min": 1.0,
            "bbox_y_min": 1.0,
            "bbox_x_max": 3.0,
            "bbox_y_max": 3.0,
        },
        {
            "object_class": "person",
            "confidence": 0.75,
            "bbox_x_min": 3.0,
            "bbox_y_min": 1.0,
            "bbox_x_max": 5.0,
            "bbox_y_max": 4.0,
        },
    ]
    assert len(detector.calls) == 2
    assert detector.calls[0]["image"].shape == (4, 6, 3)
    assert detector.calls[0]["confidence_threshold"] == 0.25
    assert detector.calls[0]["image_size"] == 640
    assert detector.calls[0]["device"] == "cuda:0"
    assert detector.calls[0]["max_detections"] == 300
    assert detector.calls[0]["half_precision"] is False
    assert processed_frames[0].annotated_image.shape == (4, 6, 3)


def test_empty_sample_sequence_produces_no_results():
    detector = FakeDetector([create_detection_result()])

    processed_frames = list(process_sampled_video_frames([], detector, MODEL_PROFILE))

    assert processed_frames == []
    assert detector.calls == []


def test_frame_with_no_detections_still_produces_result():
    sampled_frame = SampledFrame(
        frame_number=30,
        timestamp_seconds=1,
        image=np.zeros((2, 2, 3), dtype=np.uint8),
    )
    detector = FakeDetector([SimpleNamespace(names={}, boxes=[])])

    processed_frames = list(
        process_sampled_video_frames([sampled_frame], detector, MODEL_PROFILE)
    )

    assert len(processed_frames) == 1
    assert processed_frames[0].frame_number == 30
    assert processed_frames[0].detection_records == []
    assert processed_frames[0].object_counts == {}
    assert detector.calls[0]["confidence_threshold"] == 0.25
    assert detector.calls[0]["image_size"] == 1280


def test_missing_model_result_identifies_frame():
    sampled_frame = SampledFrame(
        frame_number=60,
        timestamp_seconds=2,
        image=np.zeros((2, 2, 3), dtype=np.uint8),
    )
    detector = FakeDetector([])

    with pytest.raises(ValueError, match="frame 60"):
        list(process_sampled_video_frames([sampled_frame], detector, MODEL_PROFILE))
