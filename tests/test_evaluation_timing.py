from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from evaluation.evaluation_config import TimingSettings, load_evaluation_config
from evaluation.evaluation_data import EvaluationAsset, EvaluationDataset
from evaluation.evaluation_timing import TorchDeviceMonitor, run_runtime_benchmark

CONFIG_PATH = Path("configs/evaluation/yolo26n_validation.json")


class FakeDetector:
    def __init__(self):
        self.image_values = []

    def detect(self, image, confidence_threshold, image_size, **options):
        self.image_values.append(int(image[0, 0, 0]))
        return [SimpleNamespace(names={}, boxes=[])]


class FakeDeviceMonitor:
    def __init__(self):
        self.synchronizations = 0
        self.resets = 0

    def synchronize(self):
        self.synchronizations += 1

    def reset_peak_memory(self):
        self.resets += 1

    def peak_memory_bytes(self):
        return self.resets * 1024


class StepClock:
    def __init__(self, step: float):
        self.current = 0.0
        self.step = step

    def __call__(self):
        self.current += self.step
        return self.current


def write_image(path: Path, pixel_value: int) -> None:
    image = np.full((3, 4, 3), pixel_value, dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


def create_dataset(tmp_path: Path) -> EvaluationDataset:
    assets = []
    for asset_id, pixel_value in (("first", 10), ("second", 20)):
        image_path = tmp_path / f"{asset_id}.png"
        write_image(image_path, pixel_value)
        assets.append(
            EvaluationAsset(
                asset_id=asset_id,
                collection_id="fixture",
                source_group_id=asset_id,
                dataset_role="validation",
                image_path=image_path,
                width=4,
                height=3,
                annotation_type="bounding_box",
                target_classes=frozenset({"car_or_van"}),
            )
        )
    return EvaluationDataset("validation", "1.0-draft", tuple(assets), (), ())


def test_runtime_benchmark_warms_up_and_repeats_assets_in_fixed_order(tmp_path):
    config = load_evaluation_config(CONFIG_PATH)
    config = replace(
        config,
        timing=TimingSettings(warmup_frames=1, measured_frames=3, repetitions=2),
    )
    detector = FakeDetector()
    monitor = FakeDeviceMonitor()

    result = run_runtime_benchmark(
        create_dataset(tmp_path),
        detector,
        config,
        device_monitor=monitor,
        clock=StepClock(0.01),
    )

    assert detector.image_values == [10, 10, 20, 10, 10, 20, 10]
    assert monitor.synchronizations == 14
    assert monitor.resets == 2
    assert result.warmup_frames == 1
    assert result.measured_frames_per_repetition == 3
    assert result.repetitions == 2
    assert len(result.measurements) == 6
    assert [(item.repetition, item.sample) for item in result.measurements] == [
        (1, 1),
        (1, 2),
        (1, 3),
        (2, 1),
        (2, 2),
        (2, 3),
    ]
    assert result.peak_gpu_memory_bytes_by_repetition == (1024, 2048)


def test_runtime_summary_reports_stage_latency_throughput_and_peak_memory(tmp_path):
    config = load_evaluation_config(CONFIG_PATH)
    config = replace(
        config,
        timing=TimingSettings(warmup_frames=0, measured_frames=2, repetitions=1),
    )

    result = run_runtime_benchmark(
        create_dataset(tmp_path),
        FakeDetector(),
        config,
        device_monitor=FakeDeviceMonitor(),
        clock=StepClock(0.01),
    )
    summary = result.summary

    assert summary.sample_count == 2
    assert summary.loading.median_seconds == pytest.approx(0.01)
    assert summary.preprocessing.p95_seconds == pytest.approx(0.01)
    assert summary.inference.total_seconds == pytest.approx(0.02)
    assert summary.conversion.median_seconds == pytest.approx(0.01)
    assert summary.in_memory.median_seconds == pytest.approx(0.03)
    assert summary.end_to_end.median_seconds == pytest.approx(0.04)
    assert summary.in_memory_throughput_fps == pytest.approx(100 / 3)
    assert summary.end_to_end_throughput_fps == pytest.approx(25)
    assert summary.peak_gpu_memory_bytes == 1024


def test_cpu_device_monitor_is_a_no_op():
    monitor = TorchDeviceMonitor("cpu")

    monitor.synchronize()
    monitor.reset_peak_memory()

    assert monitor.peak_memory_bytes() is None
