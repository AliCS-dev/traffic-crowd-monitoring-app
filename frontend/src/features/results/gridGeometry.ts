import type {
  GridCellResult,
  ProcessedFrameResult,
} from "../../api/analysisResults.ts";

export function gridCellLabel(cell: GridCellResult) {
  return `Row ${cell.row_index + 1}, column ${cell.column_index + 1}`;
}

export function hasAlignedGridCoordinates(
  frame: ProcessedFrameResult,
): boolean {
  const space = frame.coordinate_space;
  const asset = frame.visual_asset;
  if (
    !space ||
    !asset ||
    space.name !== "processed_image_pixels" ||
    space.origin !== "top_left" ||
    space.x_axis_direction !== "right" ||
    space.y_axis_direction !== "down" ||
    !Number.isFinite(space.width) ||
    !Number.isFinite(space.height) ||
    space.width <= 0 ||
    space.height <= 0 ||
    space.width !== asset.width ||
    space.height !== asset.height ||
    space.width !== frame.image_width ||
    space.height !== frame.image_height
  )
    return false;

  return frame.grid_cells.every(
    ({ bounds }) =>
      Object.values(bounds).every(Number.isFinite) &&
      bounds.x_min >= 0 &&
      bounds.y_min >= 0 &&
      bounds.x_max > bounds.x_min &&
      bounds.y_max > bounds.y_min &&
      bounds.x_max <= space.width &&
      bounds.y_max <= space.height,
  );
}
