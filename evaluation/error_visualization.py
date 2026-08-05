from pathlib import Path

import cv2
import numpy as np

from evaluation.evaluation_data import BoundingBox, PredictionRecord

FALSE_POSITIVE_COLOUR = (40, 40, 230)
FALSE_NEGATIVE_COLOUR = (20, 150, 255)
CONFUSION_EXPECTED_COLOUR = (220, 210, 40)
CONFUSION_PREDICTED_COLOUR = (210, 40, 210)
COUNT_PREDICTION_COLOUR = (40, 200, 80)


class ErrorVisualizationError(RuntimeError):
    """Raised when an error-analysis image cannot be rendered."""


def _load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ErrorVisualizationError(f"Could not read analysis image: {path}")
    return image


def _write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 92]):
        raise ErrorVisualizationError(f"Could not write analysis image: {path}")


def _crop_bounds(
    image: np.ndarray,
    boxes: tuple[BoundingBox, ...],
    context_multiplier: float,
) -> tuple[int, int, int, int]:
    x_min = min(box.x for box in boxes)
    y_min = min(box.y for box in boxes)
    x_max = max(box.x + box.width for box in boxes)
    y_max = max(box.y + box.height for box in boxes)
    centre_x = (x_min + x_max) / 2
    centre_y = (y_min + y_max) / 2
    extent = max(x_max - x_min, y_max - y_min, 80.0) * context_multiplier
    half = extent / 2
    left = max(0, round(centre_x - half))
    top = max(0, round(centre_y - half))
    right = min(image.shape[1], round(centre_x + half))
    bottom = min(image.shape[0], round(centre_y + half))
    if right <= left or bottom <= top:
        raise ErrorVisualizationError("Error crop has no visible area")
    return left, top, right, bottom


def _resize_crop(crop: np.ndarray, crop_size: int) -> tuple[np.ndarray, float]:
    scale = min(crop_size / crop.shape[1], crop_size / crop.shape[0], 4.0)
    if abs(scale - 1.0) < 1e-9:
        return crop, 1.0
    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    resized = cv2.resize(
        crop,
        (round(crop.shape[1] * scale), round(crop.shape[0] * scale)),
        interpolation=interpolation,
    )
    return resized, scale


def _draw_box(
    image: np.ndarray,
    box: BoundingBox,
    *,
    offset_x: int,
    offset_y: int,
    scale: float,
    colour: tuple[int, int, int],
    label: str,
) -> None:
    x_min = round((box.x - offset_x) * scale)
    y_min = round((box.y - offset_y) * scale)
    x_max = round((box.x + box.width - offset_x) * scale)
    y_max = round((box.y + box.height - offset_y) * scale)
    thickness = max(2, round(image.shape[1] / 320))
    cv2.rectangle(image, (x_min, y_min), (x_max, y_max), colour, thickness)
    font_scale = max(0.45, image.shape[1] / 1200)
    text_thickness = max(1, thickness - 1)
    text_size = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thickness
    )[0]
    text_y = max(text_size[1] + 6, y_min - 5)
    cv2.rectangle(
        image,
        (x_min, text_y - text_size[1] - 6),
        (x_min + text_size[0] + 8, text_y + 3),
        (25, 25, 25),
        -1,
    )
    cv2.putText(
        image,
        label,
        (x_min + 4, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        colour,
        text_thickness,
        cv2.LINE_AA,
    )


def _add_header(image: np.ndarray, title: str, subtitle: str) -> np.ndarray:
    header_height = 74
    output = cv2.copyMakeBorder(
        image, header_height, 0, 0, 0, cv2.BORDER_CONSTANT, value=(24, 24, 24)
    )
    font = cv2.FONT_HERSHEY_SIMPLEX
    width_scale = max(0.45, min(0.7, output.shape[1] / 1100))
    title = _fit_text(title, output.shape[1] - 24, font, width_scale, 2)
    subtitle_scale = max(0.4, width_scale - 0.08)
    subtitle = _fit_text(subtitle, output.shape[1] - 24, font, subtitle_scale, 1)
    cv2.putText(
        output,
        title,
        (12, 29),
        font,
        width_scale,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        output,
        subtitle,
        (12, 57),
        font,
        subtitle_scale,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )
    return output


def _fit_text(
    value: str,
    max_width: int,
    font: int,
    font_scale: float,
    thickness: int,
) -> str:
    if cv2.getTextSize(value, font, font_scale, thickness)[0][0] <= max_width:
        return value
    suffix = "..."
    shortened = value
    while (
        shortened
        and cv2.getTextSize(shortened + suffix, font, font_scale, thickness)[0][0]
        > max_width
    ):
        shortened = shortened[:-1]
    return shortened + suffix


def render_detection_error(
    image_path: Path,
    output_path: Path,
    *,
    asset_id: str,
    error_type: str,
    expected_class: str | None,
    predicted_class: str | None,
    confidence: float | None,
    iou: float | None,
    ground_truth_box: BoundingBox | None,
    prediction_box: BoundingBox | None,
    crop_size: int,
    context_multiplier: float,
) -> None:
    image = _load_image(image_path)
    boxes = tuple(box for box in (ground_truth_box, prediction_box) if box is not None)
    if not boxes:
        raise ErrorVisualizationError("Detection error has no box to render")
    left, top, right, bottom = _crop_bounds(image, boxes, context_multiplier)
    crop, scale = _resize_crop(image[top:bottom, left:right].copy(), crop_size)

    if error_type == "false_positive" and prediction_box is not None:
        _draw_box(
            crop,
            prediction_box,
            offset_x=left,
            offset_y=top,
            scale=scale,
            colour=FALSE_POSITIVE_COLOUR,
            label=f"FP {predicted_class} {confidence:.2f}",
        )
    elif error_type == "false_negative" and ground_truth_box is not None:
        _draw_box(
            crop,
            ground_truth_box,
            offset_x=left,
            offset_y=top,
            scale=scale,
            colour=FALSE_NEGATIVE_COLOUR,
            label=f"FN {expected_class}",
        )
    elif (
        error_type in {"class_confusion", "excluded_label_confusion"}
        and ground_truth_box is not None
        and prediction_box is not None
    ):
        _draw_box(
            crop,
            ground_truth_box,
            offset_x=left,
            offset_y=top,
            scale=scale,
            colour=CONFUSION_EXPECTED_COLOUR,
            label=f"GT {expected_class}",
        )
        _draw_box(
            crop,
            prediction_box,
            offset_x=left,
            offset_y=top,
            scale=scale,
            colour=CONFUSION_PREDICTED_COLOUR,
            label=f"PRED {predicted_class} {confidence:.2f}",
        )
    else:
        raise ErrorVisualizationError(f"Unsupported detection error: {error_type}")

    details = []
    if confidence is not None:
        details.append(f"confidence {confidence:.3f}")
    if iou is not None:
        details.append(f"IoU {iou:.3f}")
    display_type = error_type.replace("_", " ")
    output = _add_header(crop, f"{display_type}: {asset_id}", " | ".join(details))
    _write_image(output_path, output)


def render_count_error(
    image_path: Path,
    output_path: Path,
    *,
    asset_id: str,
    ground_truth_count: int,
    predicted_count: int,
    predictions: tuple[PredictionRecord, ...],
    max_width: int = 1600,
) -> None:
    image = _load_image(image_path)
    scale = min(1.0, max_width / image.shape[1])
    if scale < 1:
        image = cv2.resize(
            image,
            (round(image.shape[1] * scale), round(image.shape[0] * scale)),
            interpolation=cv2.INTER_AREA,
        )
    for prediction in predictions:
        _draw_box(
            image,
            prediction.box,
            offset_x=0,
            offset_y=0,
            scale=scale,
            colour=COUNT_PREDICTION_COLOUR,
            label=f"person {prediction.confidence:.2f}",
        )
    signed_error = predicted_count - ground_truth_count
    subtitle = (
        f"ground truth {ground_truth_count} | predicted {predicted_count} | "
        f"signed error {signed_error:+d}"
    )
    output = _add_header(image, f"count error: {asset_id}", subtitle)
    _write_image(output_path, output)


def render_contact_sheet(
    image_paths: tuple[Path, ...],
    output_path: Path,
    *,
    columns: int = 3,
    cell_width: int = 480,
    cell_height: int = 380,
) -> None:
    if not image_paths:
        raise ErrorVisualizationError("Contact sheet requires at least one image")
    rows = (len(image_paths) + columns - 1) // columns
    sheet = np.full((rows * cell_height, columns * cell_width, 3), 28, dtype=np.uint8)
    for index, path in enumerate(image_paths):
        image = _load_image(path)
        scale = min(cell_width / image.shape[1], cell_height / image.shape[0])
        resized = cv2.resize(
            image,
            (round(image.shape[1] * scale), round(image.shape[0] * scale)),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
        )
        row, column = divmod(index, columns)
        x = column * cell_width + (cell_width - resized.shape[1]) // 2
        y = row * cell_height + (cell_height - resized.shape[0]) // 2
        sheet[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    _write_image(output_path, sheet)
