import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from types import MappingProxyType


@dataclass(frozen=True)
class GridSize:
    rows: int
    columns: int

    def __post_init__(self) -> None:
        _validate_positive_integer(self.rows, "Grid rows")
        _validate_positive_integer(self.columns, "Grid columns")


@dataclass(frozen=True)
class GridCellCount:
    row_index: int
    column_index: int
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    object_counts: Mapping[str, int]

    @property
    def total_count(self) -> int:
        return sum(self.object_counts.values())


@dataclass(frozen=True)
class GridCountResult:
    image_width: int
    image_height: int
    grid_size: GridSize
    cells: tuple[GridCellCount, ...]

    @property
    def total_count(self) -> int:
        return sum(cell.total_count for cell in self.cells)

    def get_cell(self, row_index: int, column_index: int) -> GridCellCount:
        if not 0 <= row_index < self.grid_size.rows:
            raise IndexError("Grid row index is outside the configured grid.")
        if not 0 <= column_index < self.grid_size.columns:
            raise IndexError("Grid column index is outside the configured grid.")
        return self.cells[row_index * self.grid_size.columns + column_index]


def count_detections_by_grid(
    detection_records: Sequence[Mapping[str, object]],
    image_width: int,
    image_height: int,
    *,
    rows: int,
    columns: int,
) -> GridCountResult:
    _validate_positive_integer(image_width, "Image width")
    _validate_positive_integer(image_height, "Image height")
    grid_size = GridSize(rows=rows, columns=columns)
    cell_counts: list[Counter[str]] = [Counter() for _ in range(rows * columns)]

    for record_index, record in enumerate(detection_records):
        object_class, centre_x, centre_y = _detection_centre(
            record,
            record_index,
            image_width,
            image_height,
        )
        column_index = min(int(centre_x * columns / image_width), columns - 1)
        row_index = min(int(centre_y * rows / image_height), rows - 1)
        cell_counts[row_index * columns + column_index][object_class] += 1

    cells: list[GridCellCount] = []
    for row_index in range(rows):
        for column_index in range(columns):
            counts = cell_counts[row_index * columns + column_index]
            cells.append(
                GridCellCount(
                    row_index=row_index,
                    column_index=column_index,
                    x_min=column_index * image_width / columns,
                    y_min=row_index * image_height / rows,
                    x_max=(column_index + 1) * image_width / columns,
                    y_max=(row_index + 1) * image_height / rows,
                    object_counts=MappingProxyType(dict(sorted(counts.items()))),
                )
            )

    return GridCountResult(
        image_width=image_width,
        image_height=image_height,
        grid_size=grid_size,
        cells=tuple(cells),
    )


def _validate_positive_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer.")


def _detection_centre(
    record: Mapping[str, object],
    record_index: int,
    image_width: int,
    image_height: int,
) -> tuple[str, float, float]:
    if not isinstance(record, Mapping):
        raise ValueError(f"Detection record {record_index} must be a mapping.")

    object_class = record.get("object_class")
    if not isinstance(object_class, str) or not object_class.strip():
        raise ValueError(
            f"Detection record {record_index} must have a non-empty object_class."
        )

    x_min = _coordinate(record, "bbox_x_min", record_index)
    y_min = _coordinate(record, "bbox_y_min", record_index)
    x_max = _coordinate(record, "bbox_x_max", record_index)
    y_max = _coordinate(record, "bbox_y_max", record_index)

    if not 0 <= x_min <= x_max <= image_width:
        raise ValueError(
            f"Detection record {record_index} has horizontal bounds outside the image."
        )
    if not 0 <= y_min <= y_max <= image_height:
        raise ValueError(
            f"Detection record {record_index} has vertical bounds outside the image."
        )

    return object_class.strip(), (x_min + x_max) / 2, (y_min + y_max) / 2


def _coordinate(
    record: Mapping[str, object], field_name: str, record_index: int
) -> float:
    value = record.get(field_name)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(
            f"Detection record {record_index} must have a numeric {field_name}."
        )
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(
            f"Detection record {record_index} must have a finite {field_name}."
        )
    return number
