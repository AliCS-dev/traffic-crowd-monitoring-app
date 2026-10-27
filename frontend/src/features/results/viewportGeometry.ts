export interface ViewTransform {
  zoom: number;
  x: number;
  y: number;
}

export function fitImage(
  width: number,
  height: number,
  imageWidth: number,
  imageHeight: number,
) {
  const scale = Math.min(width / imageWidth, height / imageHeight);
  return { width: imageWidth * scale, height: imageHeight * scale };
}

export function constrainView(
  view: ViewTransform,
  image: { width: number; height: number },
  viewport: { width: number; height: number },
): ViewTransform {
  const zoom = Math.min(8, Math.max(1, view.zoom));
  const limitX = Math.max(0, (image.width * zoom - viewport.width) / 2);
  const limitY = Math.max(0, (image.height * zoom - viewport.height) / 2);
  return {
    zoom,
    x: limitX === 0 ? 0 : Math.min(limitX, Math.max(-limitX, view.x)),
    y: limitY === 0 ? 0 : Math.min(limitY, Math.max(-limitY, view.y)),
  };
}
