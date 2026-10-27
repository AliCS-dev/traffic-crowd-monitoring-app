import { describe, expect, it } from "vitest";
import { constrainView, fitImage } from "./viewportGeometry.ts";

describe("scene geometry", () => {
  it("fits wide and portrait images without cropping or distortion", () => {
    expect(fitImage(800, 600, 1600, 900)).toEqual({ width: 800, height: 450 });
    expect(fitImage(800, 600, 600, 1200)).toEqual({ width: 300, height: 600 });
  });
  it("bounds zoom and pan, including after viewport resize", () => {
    expect(
      constrainView(
        { zoom: 0.5, x: 100, y: -50 },
        { width: 800, height: 450 },
        { width: 800, height: 600 },
      ),
    ).toEqual({ zoom: 1, x: 0, y: 0 });
    expect(
      constrainView(
        { zoom: 2, x: 1000, y: -1000 },
        { width: 800, height: 450 },
        { width: 800, height: 600 },
      ),
    ).toEqual({ zoom: 2, x: 400, y: -150 });
    expect(
      constrainView(
        { zoom: 10, x: 0, y: 0 },
        { width: 300, height: 600 },
        { width: 800, height: 600 },
      ).zoom,
    ).toBe(8);
  });
});
