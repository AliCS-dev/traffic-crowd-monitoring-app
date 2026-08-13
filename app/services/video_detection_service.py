from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from app.model_profile import RuntimeModelProfile
from app.services.detection_service import (
    ObjectDetector,
    count_detected_objects,
    detect_objects_with_profile,
    extract_detection_records,
)
from app.services.frame_sampling_service import SampledFrame
from app.services.preprocessing_service import preprocess_image_for_detection


@dataclass(frozen=True)
class VideoFrameDetectionResult:
    frame_number: int
    timestamp_seconds: float
    image_width: int
    image_height: int
    detection_records: list[dict]
    object_counts: dict[str, int]


def process_sampled_video_frames(
    sampled_frames: Iterable[SampledFrame],
    detector: ObjectDetector,
    profile: RuntimeModelProfile,
) -> Iterator[VideoFrameDetectionResult]:
    class_mapping = profile.class_mapping_dict()
    for sampled_frame in sampled_frames:
        processed_image = preprocess_image_for_detection(
            sampled_frame.image,
            scale_factor=profile.scale_factor,
        )
        results = detect_objects_with_profile(
            processed_image,
            detector,
            profile,
        )

        if not results:
            raise ValueError(
                f"Detection produced no result for frame {sampled_frame.frame_number}."
            )

        first_result = results[0]
        image_height, image_width = processed_image.shape[:2]

        yield VideoFrameDetectionResult(
            frame_number=sampled_frame.frame_number,
            timestamp_seconds=sampled_frame.timestamp_seconds,
            image_width=image_width,
            image_height=image_height,
            detection_records=extract_detection_records(first_result, class_mapping),
            object_counts=count_detected_objects(first_result, class_mapping),
        )
