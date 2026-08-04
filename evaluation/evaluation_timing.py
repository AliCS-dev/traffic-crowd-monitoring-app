from collections.abc import Callable
from dataclasses import dataclass
from itertools import cycle, islice
from statistics import median
from time import perf_counter
from typing import Protocol

from evaluation.evaluation_config import EvaluationConfig
from evaluation.evaluation_data import EvaluationAsset, EvaluationDataset
from evaluation.evaluation_runner import (
    Detector,
    convert_evaluation_result,
    detect_evaluation_image,
    load_evaluation_image,
    preprocess_evaluation_image,
    validate_dataset_configuration,
)


class EvaluationTimingError(RuntimeError):
    """Raised when the configured timing device cannot be measured."""


class DeviceMonitor(Protocol):
    def synchronize(self) -> None: ...

    def reset_peak_memory(self) -> None: ...

    def peak_memory_bytes(self) -> int | None: ...


class TorchDeviceMonitor:
    """Synchronize inference and collect CUDA memory without affecting CPU runs."""

    def __init__(self, device: str):
        import torch

        self._torch = torch
        self._device = torch.device(device)
        if self._device.type == "cuda":
            if not torch.cuda.is_available():
                raise EvaluationTimingError(
                    f"CUDA timing was requested for {device}, but CUDA is unavailable"
                )
            index = self._device.index
            if index is None:
                index = torch.cuda.current_device()
            if index >= torch.cuda.device_count():
                raise EvaluationTimingError(
                    f"CUDA device index is unavailable: {index}"
                )
            self._device = torch.device("cuda", index)
        elif self._device.type != "cpu":
            raise EvaluationTimingError(
                "Runtime measurement does not support device type "
                f"{self._device.type!r}"
            )

    def synchronize(self) -> None:
        if self._device.type == "cuda":
            self._torch.cuda.synchronize(self._device)

    def reset_peak_memory(self) -> None:
        if self._device.type == "cuda":
            self._torch.cuda.reset_peak_memory_stats(self._device)

    def peak_memory_bytes(self) -> int | None:
        if self._device.type != "cuda":
            return None
        return int(self._torch.cuda.max_memory_allocated(self._device))


@dataclass(frozen=True)
class StageStatistics:
    median_seconds: float
    p95_seconds: float
    total_seconds: float


@dataclass(frozen=True)
class RuntimeMeasurement:
    repetition: int
    sample: int
    asset_id: str
    loading_seconds: float
    preprocessing_seconds: float
    inference_seconds: float
    conversion_seconds: float
    in_memory_seconds: float
    end_to_end_seconds: float


@dataclass(frozen=True)
class RuntimeSummary:
    sample_count: int
    loading: StageStatistics
    preprocessing: StageStatistics
    inference: StageStatistics
    conversion: StageStatistics
    in_memory: StageStatistics
    end_to_end: StageStatistics
    in_memory_throughput_fps: float
    end_to_end_throughput_fps: float
    peak_gpu_memory_bytes: int | None


@dataclass(frozen=True)
class RuntimeBenchmarkResult:
    warmup_frames: int
    measured_frames_per_repetition: int
    repetitions: int
    measurements: tuple[RuntimeMeasurement, ...]
    peak_gpu_memory_bytes_by_repetition: tuple[int | None, ...]
    summary: RuntimeSummary


def _percentile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _stage_statistics(values: tuple[float, ...]) -> StageStatistics:
    return StageStatistics(
        median_seconds=median(values),
        p95_seconds=_percentile(values, 0.95),
        total_seconds=sum(values),
    )


def _run_warmup_asset(
    asset: EvaluationAsset,
    detector: Detector,
    config: EvaluationConfig,
    monitor: DeviceMonitor,
) -> None:
    image = load_evaluation_image(asset)
    processed_image = preprocess_evaluation_image(image, config)
    monitor.synchronize()
    result = detect_evaluation_image(asset.asset_id, processed_image, detector, config)
    monitor.synchronize()
    convert_evaluation_result(result, asset, config)


def _measure_asset(
    asset: EvaluationAsset,
    repetition: int,
    sample: int,
    detector: Detector,
    config: EvaluationConfig,
    monitor: DeviceMonitor,
    clock: Callable[[], float],
) -> RuntimeMeasurement:
    start = clock()
    image = load_evaluation_image(asset)
    loading_seconds = clock() - start

    start = clock()
    processed_image = preprocess_evaluation_image(image, config)
    preprocessing_seconds = clock() - start

    monitor.synchronize()
    start = clock()
    result = detect_evaluation_image(asset.asset_id, processed_image, detector, config)
    monitor.synchronize()
    inference_seconds = clock() - start

    start = clock()
    convert_evaluation_result(result, asset, config)
    conversion_seconds = clock() - start

    in_memory_seconds = preprocessing_seconds + inference_seconds + conversion_seconds
    return RuntimeMeasurement(
        repetition=repetition,
        sample=sample,
        asset_id=asset.asset_id,
        loading_seconds=loading_seconds,
        preprocessing_seconds=preprocessing_seconds,
        inference_seconds=inference_seconds,
        conversion_seconds=conversion_seconds,
        in_memory_seconds=in_memory_seconds,
        end_to_end_seconds=loading_seconds + in_memory_seconds,
    )


def _summarize_runtime(
    measurements: tuple[RuntimeMeasurement, ...],
    repetition_peaks: tuple[int | None, ...],
) -> RuntimeSummary:
    loading = _stage_statistics(tuple(item.loading_seconds for item in measurements))
    preprocessing = _stage_statistics(
        tuple(item.preprocessing_seconds for item in measurements)
    )
    inference = _stage_statistics(
        tuple(item.inference_seconds for item in measurements)
    )
    conversion = _stage_statistics(
        tuple(item.conversion_seconds for item in measurements)
    )
    in_memory = _stage_statistics(
        tuple(item.in_memory_seconds for item in measurements)
    )
    end_to_end = _stage_statistics(
        tuple(item.end_to_end_seconds for item in measurements)
    )
    measured_peaks = tuple(value for value in repetition_peaks if value is not None)
    return RuntimeSummary(
        sample_count=len(measurements),
        loading=loading,
        preprocessing=preprocessing,
        inference=inference,
        conversion=conversion,
        in_memory=in_memory,
        end_to_end=end_to_end,
        in_memory_throughput_fps=len(measurements) / in_memory.total_seconds,
        end_to_end_throughput_fps=len(measurements) / end_to_end.total_seconds,
        peak_gpu_memory_bytes=max(measured_peaks) if measured_peaks else None,
    )


def run_runtime_benchmark(
    dataset: EvaluationDataset,
    detector: Detector,
    config: EvaluationConfig,
    *,
    device_monitor: DeviceMonitor | None = None,
    clock: Callable[[], float] = perf_counter,
) -> RuntimeBenchmarkResult:
    validate_dataset_configuration(dataset, config)
    monitor = device_monitor or TorchDeviceMonitor(config.inference.device)

    warmup_assets = islice(cycle(dataset.assets), config.timing.warmup_frames)
    for asset in warmup_assets:
        _run_warmup_asset(asset, detector, config, monitor)

    measurements = []
    repetition_peaks = []
    for repetition in range(1, config.timing.repetitions + 1):
        monitor.reset_peak_memory()
        measured_assets = islice(cycle(dataset.assets), config.timing.measured_frames)
        for sample, asset in enumerate(measured_assets, start=1):
            measurements.append(
                _measure_asset(
                    asset,
                    repetition,
                    sample,
                    detector,
                    config,
                    monitor,
                    clock,
                )
            )
        repetition_peaks.append(monitor.peak_memory_bytes())

    measurement_tuple = tuple(measurements)
    repetition_peak_tuple = tuple(repetition_peaks)
    return RuntimeBenchmarkResult(
        warmup_frames=config.timing.warmup_frames,
        measured_frames_per_repetition=config.timing.measured_frames,
        repetitions=config.timing.repetitions,
        measurements=measurement_tuple,
        peak_gpu_memory_bytes_by_repetition=repetition_peak_tuple,
        summary=_summarize_runtime(measurement_tuple, repetition_peak_tuple),
    )
