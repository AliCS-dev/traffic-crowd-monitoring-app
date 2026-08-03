from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from evaluation.dataset_validation import read_csv


@dataclass(frozen=True)
class ContactSheetItem:
    asset_id: str
    preview_path: Path


def letterbox(image: np.ndarray, width: int, height: int) -> np.ndarray:
    scale = min(width / image.shape[1], height / image.shape[0])
    resized = cv2.resize(
        image,
        (round(image.shape[1] * scale), round(image.shape[0] * scale)),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )
    canvas = np.full((height, width, 3), 28, dtype=np.uint8)
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def fit_text_scale(text: str, max_width: int, initial_scale: float = 0.5) -> float:
    scale = initial_scale
    while scale > 0.3:
        text_width = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
        if text_width <= max_width:
            return scale
        scale -= 0.025
    return 0.3


def make_contact_sheet(
    title: str,
    items: list[tuple[str, np.ndarray]],
    columns: int = 3,
    rows: int = 4,
    cell_width: int = 480,
    image_height: int = 270,
) -> np.ndarray:
    title_height = 44
    label_height = 34
    sheet = np.full(
        (
            title_height + rows * (image_height + label_height),
            columns * cell_width,
            3,
        ),
        22,
        dtype=np.uint8,
    )
    cv2.putText(
        sheet,
        title,
        (12, 29),
        cv2.FONT_HERSHEY_SIMPLEX,
        fit_text_scale(title, sheet.shape[1] - 24, 0.7),
        (245, 245, 245),
        1,
        cv2.LINE_AA,
    )

    for index, (asset_id, image) in enumerate(items):
        row, column = divmod(index, columns)
        x = column * cell_width
        y = title_height + row * (image_height + label_height)
        sheet[y : y + image_height, x : x + cell_width] = letterbox(
            image, cell_width, image_height
        )
        cv2.putText(
            sheet,
            asset_id,
            (x + 8, y + image_height + 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            fit_text_scale(asset_id, cell_width - 16),
            (235, 235, 235),
            1,
            cv2.LINE_AA,
        )
    return sheet


def chunks(items: list[ContactSheetItem], size: int) -> list[list[ContactSheetItem]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def render_contact_sheets(
    repository_root: Path, only_unreviewed: bool = True
) -> list[dict[str, str | int]]:
    _, manifest = read_csv(repository_root / "data/evaluation/manifest.csv")
    _, preview_rows = read_csv(
        repository_root / "data/evaluation/derived/previews/preview_index.csv"
    )
    _, review_rows = read_csv(repository_root / "data/evaluation/qc_reviews.csv")
    reviewed_ids = {row["asset_id"] for row in review_rows}
    manifest_by_asset = {row["asset_id"]: row for row in manifest}

    groups: dict[tuple[str, str], list[ContactSheetItem]] = defaultdict(list)
    for preview in preview_rows:
        asset_id = preview["asset_id"]
        if only_unreviewed and asset_id in reviewed_ids:
            continue
        record = manifest_by_asset[asset_id]
        groups[(record["collection_id"], record["dataset_role"])].append(
            ContactSheetItem(
                asset_id=asset_id,
                preview_path=repository_root / preview["preview_path"],
            )
        )

    output_root = repository_root / "data/evaluation/derived/qc_contact_sheets"
    output_root.mkdir(parents=True, exist_ok=True)
    expected_paths: set[Path] = set()
    index_rows: list[dict[str, str | int]] = []
    page_size = 12

    for (collection_id, role), group_items in sorted(groups.items()):
        group_items.sort(key=lambda item: item.asset_id)
        pages = chunks(group_items, page_size)
        for page_number, page_items in enumerate(pages, start=1):
            images = []
            for item in page_items:
                image = cv2.imread(str(item.preview_path))
                if image is None:
                    raise ValueError(f"Cannot read preview: {item.preview_path}")
                images.append((item.asset_id, image))

            title = f"{collection_id} / {role} / page {page_number} of {len(pages)}"
            sheet = make_contact_sheet(title, images)
            output_path = output_root / (
                f"{collection_id}_{role}_{page_number:02d}.jpg"
            )
            expected_paths.add(output_path)
            if not cv2.imwrite(str(output_path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90]):
                raise ValueError(f"Cannot write contact sheet: {output_path}")
            index_rows.append(
                {
                    "collection_id": collection_id,
                    "dataset_role": role,
                    "page": page_number,
                    "asset_count": len(page_items),
                    "first_asset_id": page_items[0].asset_id,
                    "last_asset_id": page_items[-1].asset_id,
                    "sheet_path": output_path.relative_to(repository_root).as_posix(),
                }
            )

    for stale_path in output_root.glob("*.jpg"):
        if stale_path not in expected_paths:
            stale_path.unlink()

    index_path = output_root / "contact_sheet_index.csv"
    with index_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "collection_id",
                "dataset_role",
                "page",
                "asset_count",
                "first_asset_id",
                "last_asset_id",
                "sheet_path",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(index_rows)
    return index_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render labelled contact sheets for evaluation QC."
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--include-reviewed",
        action="store_true",
        help="Include assets that already have a QC decision.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = render_contact_sheets(
        args.repository_root.resolve(), only_unreviewed=not args.include_reviewed
    )
    print(
        f"Rendered {len(rows)} contact sheets containing "
        f"{sum(int(row['asset_count']) for row in rows)} assets"
    )


if __name__ == "__main__":
    main()
