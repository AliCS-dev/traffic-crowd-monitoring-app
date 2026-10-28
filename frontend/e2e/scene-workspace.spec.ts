import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { gridResultFixture } from "../src/test/analysisResultFixture.ts";

const sampleImage = fileURLToPath(
  new URL("../../data/input/sample_image.jpg", import.meta.url),
);

async function openScene(page: Page, count = 3) {
  const result = gridResultFixture();
  result.session_name = "Scene inspection fixture";
  const frame = result.frames[0];
  for (const { bounds } of [...frame.grid_cells, ...frame.detections]) {
    for (const key of ["x_min", "x_max"] as const) bounds[key] *= 590 / 1280;
    for (const key of ["y_min", "y_max"] as const) bounds[key] *= 332 / 720;
  }
  frame.image_width =
    frame.coordinate_space!.width =
    frame.visual_asset!.width =
      590;
  frame.image_height =
    frame.coordinate_space!.height =
    frame.visual_asset!.height =
      332;
  frame.source_asset = {
    ...frame.visual_asset!,
    url: `${frame.visual_asset!.url}/source`,
    rendered_overlays: [],
  };
  if (count > 3)
    frame.detections = Array.from({ length: count }, (_, index) => ({
      ...frame.detections[index % 3],
      id: index + 100,
    }));
  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: { status: "ok", service: "Test API", version: "1" },
    }),
  );
  await page.route("**/api/analyses/42", (route) =>
    route.fulfill({ json: result }),
  );
  await page.route("**/api/assets/*/source", (route) =>
    route.fulfill({ path: sampleImage, contentType: "image/jpeg" }),
  );
  await page.goto("/analyses/42");
  await expect(
    page.getByRole("group", { name: "Detection overlays" }),
  ).toBeVisible();
  return frame;
}

async function checkAlignment(page: Page, timeout = 5000) {
  const detection = gridResultFixture().frames[0].detections[0];
  await expect(async () => {
    // Read one layout snapshot; separate browser calls can straddle a resize.
    const { image, cell, box, fittedWidth, expectedWidth, overflow } =
      await page.locator("[data-scene-stage]").evaluate((stage, id) => {
        const image = stage.querySelector("img")!.getBoundingClientRect();
        const cell = stage
          .querySelector('[aria-label="Row 1, column 2"]')!
          .getBoundingClientRect();
        const box = stage
          .querySelector(`[aria-label^="Detection ${id}:"]`)!
          .getBoundingClientRect();
        const viewport = stage.parentElement!.getBoundingClientRect();
        return {
          image: image.toJSON(),
          cell: cell.toJSON(),
          box: box.toJSON(),
          fittedWidth: parseFloat(getComputedStyle(stage).width),
          expectedWidth:
            Math.min(viewport.width / 590, viewport.height / 332) * 590,
          overflow: document.documentElement.scrollWidth > innerWidth,
        };
      }, detection.id);
    expect(Math.abs(fittedWidth - expectedWidth)).toBeLessThan(1);
    expect(image.width).toBeGreaterThan(0);
    expect(image.height).toBeGreaterThan(0);
    expect(Math.abs(image.width / image.height - 590 / 332)).toBeLessThan(0.01);
    expect(Math.abs(cell.x - image.x - image.width / 2)).toBeLessThan(1);
    expect(Math.abs(cell.y - image.y)).toBeLessThan(1);
    expect(Math.abs(cell.width - image.width / 2)).toBeLessThan(1);
    expect(Math.abs(cell.height - image.height / 2)).toBeLessThan(1);
    expect(
      Math.abs(box.x - image.x - (image.width * detection.bounds.x_min) / 1280),
    ).toBeLessThan(1);
    expect(
      Math.abs(box.y - image.y - (image.height * detection.bounds.y_min) / 720),
    ).toBeLessThan(1);
    expect(
      Math.abs(
        box.width -
          (image.width * (detection.bounds.x_max - detection.bounds.x_min)) /
            1280,
      ),
    ).toBeLessThan(1);
    expect(
      Math.abs(
        box.height -
          (image.height * (detection.bounds.y_max - detection.bounds.y_min)) /
            720,
      ),
    ).toBeLessThan(1);
    expect(overflow).toBe(false);
  }).toPass({ timeout, intervals: [50, 100, 250] });
}

test("alignment check rejects a persistently displaced grid cell", async ({
  page,
}) => {
  await openScene(page);
  await checkAlignment(page);
  const cell = page.getByRole("button", {
    name: "Row 1, column 2",
    exact: true,
  });
  await cell.evaluate((element) => {
    element.style.transform = "translateX(10px)";
  });
  await expect(checkAlignment(page, 300)).rejects.toThrow("toBeLessThan");
  await cell.evaluate((element) => {
    element.style.removeProperty("transform");
  });
  await checkAlignment(page);
});

test("scene selection, zoom, pan, resize and display filters stay aligned", async ({
  page,
}) => {
  page.on("pageerror", (error) => {
    throw error;
  });
  const frame = await openScene(page);
  await checkAlignment(page);
  const first = frame.detections[0];
  await page
    .getByRole("button", { name: `Inspect detection ${first.id}` })
    .click();
  const box = page.getByRole("button", {
    name: new RegExp(`^Detection ${first.id}:`),
  });
  await expect(box).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("complementary")).toContainText(
    `Detection ${first.id}`,
  );
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await checkAlignment(page);
  await page.getByRole("button", { name: "Pan image" }).click();
  const viewport = page.getByRole("group", { name: "Scene viewport" });
  await viewport.focus();
  await page.keyboard.press("ArrowLeft");
  await checkAlignment(page);
  const size = page.viewportSize()!;
  await page.setViewportSize({
    width: size.width === 320 ? 390 : 1280,
    height: size.height,
  });
  await checkAlignment(page);
  await page.getByRole("button", { name: "Fit image" }).click();
  await page.getByRole("button", { name: "Select objects" }).click();
  await page
    .getByRole("combobox", { name: "Class filter" })
    .selectOption("person");
  await expect(
    page.getByRole("group", { name: "Detection overlays" }).getByRole("button"),
  ).toHaveCount(2);
  await expect(
    page.getByText("2 matching records / 3 stored detections"),
  ).toBeVisible();
  await page.getByRole("switch", { name: "Detections", exact: true }).click();
  await expect(
    page.getByRole("group", { name: "Detection overlays" }),
  ).toHaveCount(0);
  await page.getByRole("switch", { name: "Detections", exact: true }).click();
  await page.getByRole("combobox", { name: "Class filter" }).selectOption("");
  await page.setViewportSize(size);
  await page.getByRole("button", { name: "Fit image" }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.mouse.move(0, 0);
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await expect(page).toHaveScreenshot("scene-workspace.png", {
    fullPage: true,
  });
});

test("300 detection overlays remain within the interaction budget", async ({
  page,
}) => {
  await openScene(page, 300);
  const start = performance.now();
  await page
    .getByRole("combobox", { name: "Class filter" })
    .selectOption("person");
  await expect(
    page.getByRole("group", { name: "Detection overlays" }).getByRole("button"),
  ).toHaveCount(200);
  const elapsed = performance.now() - start;
  // Includes Playwright and assertion overhead; this is a generous regression ceiling.
  expect(elapsed).toBeLessThan(2000);
  test.info().annotations.push({
    type: "filter-duration-ms",
    description: elapsed.toFixed(1),
  });
});

test("touch panning keeps the scene and boxes together", async ({
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: "http://localhost:5174",
    viewport: { width: 390, height: 844 },
    hasTouch: true,
  });
  try {
    const page = await context.newPage();
    await openScene(page);
    await page.getByRole("button", { name: "Zoom in", exact: true }).tap();
    await page.getByRole("button", { name: "Zoom in", exact: true }).tap();
    await page.getByRole("button", { name: "Pan image" }).tap();
    const viewport = page.getByRole("group", { name: "Scene viewport" });
    await viewport.scrollIntoViewIfNeeded();
    const rect = (await viewport.boundingBox())!;
    const stage = page.locator("[data-scene-stage]");
    const before = await stage.evaluate(
      (element) => getComputedStyle(element).transform,
    );
    const cdp = await context.newCDPSession(page);
    const x = rect.x + rect.width / 2,
      y = rect.y + rect.height / 2;
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x, y }],
    });
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x: x + 45, y: y + 15 }],
    });
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchEnd",
      touchPoints: [],
    });
    await expect
      .poll(() =>
        stage.evaluate((element) => getComputedStyle(element).transform),
      )
      .not.toBe(before);
    await checkAlignment(page);
  } finally {
    await context.close();
  }
});
