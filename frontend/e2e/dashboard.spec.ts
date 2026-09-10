import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { alertResultFixture } from "../src/test/alertResultFixture.ts";
import { videoResultFixture } from "../src/test/analysisResultFixture.ts";

const sampleImage = fileURLToPath(
  new URL("../../data/input/sample_image.jpg", import.meta.url),
);

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => {
    throw error;
  });
  await page.route("http://localhost:8000/api/**", (route) =>
    route.fulfill({ status: 503, json: { error: { message: "Unavailable" } } }),
  );
  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: { status: "ok", service: "Test API", version: "1" },
    }),
  );
});

test("session history recovers from an unavailable API into an empty state", async ({
  page,
}) => {
  await page.goto("/sessions");
  await expect(
    page.getByRole("heading", { name: "Session history unavailable" }),
  ).toBeVisible({ timeout: 15000 });
  await page.route("**/api/analyses?*", (route) =>
    route.fulfill({
      json: {
        items: [],
        pagination: { page: 1, page_size: 20, total_items: 0, total_pages: 0 },
      },
    }),
  );
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "No sessions available" }),
  ).toBeVisible();
  await checkPageWidth(page);
});

async function checkPageWidth(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const info = await page
    .getByRole("button", { name: "Application information" })
    .boundingBox();
  expect(info).not.toBeNull();
  expect(info!.x + info!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
}

test("image grid stays aligned, keyboard inspection and table filters preserve alert scope", async ({
  page,
}) => {
  const result = alertResultFixture();
  const frame = result.frames[0];
  // Match the tracked sample image; these are presentation fixtures, not predictions.
  for (const { bounds } of [...frame.grid_cells, ...frame.detections]) {
    for (const key of ["x_min", "x_max"] as const) bounds[key] *= 590 / 1280;
    for (const key of ["y_min", "y_max"] as const) bounds[key] *= 332 / 720;
  }
  frame.image_width =
    frame.visual_asset!.width =
    frame.coordinate_space!.width =
      590;
  frame.image_height =
    frame.visual_asset!.height =
    frame.coordinate_space!.height =
      332;
  frame.visual_asset!.rendered_overlays = [];
  await page.route("**/api/analyses/42", (route) =>
    route.fulfill({ json: result }),
  );
  await page.route("**/api/assets/*", (route) =>
    route.fulfill({ path: sampleImage, contentType: "image/jpeg" }),
  );
  await page.goto("/analyses/42");
  const grid = page.getByRole("group", { name: "Image grid" });
  await expect(grid).toBeVisible();
  const image = page.getByRole("img", {
    name: "Detection result for junction.jpg",
  });
  const imageBox = (await image.boundingBox())!;
  expect(Math.abs(imageBox.width / imageBox.height - 590 / 332)).toBeLessThan(
    0.01,
  );
  const cell = grid.getByRole("button", {
    name: "Row 1, column 2",
    exact: true,
  });
  const cellBox = (await cell.boundingBox())!;
  expect(Math.abs(cellBox.x - imageBox.x - imageBox.width / 2)).toBeLessThan(1);
  expect(Math.abs(cellBox.width - imageBox.width / 2)).toBeLessThan(1);
  expect(Math.abs(cellBox.height - imageBox.height / 2)).toBeLessThan(1);
  await checkPageWidth(page);
  // Move the figure below the fixed toolbar before capturing its layout.
  await image.evaluate((element) => {
    element.closest("figure")!.scrollIntoView();
    window.scrollBy(0, -100);
  });
  await expect(page.locator("figure")).toHaveScreenshot("image-grid.png");
  const events = page.getByRole("region", { name: "Experimental alerts" });
  await page
    .getByRole("combobox", { name: "Table class" })
    .selectOption("car_or_van");
  await expect(events.getByRole("article")).toHaveCount(2);
  const inspect = events.getByRole("button", {
    name: "Inspect row 1, column 2",
  });
  await inspect.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("combobox", { name: "Grid cell" })).toHaveValue(
    "51",
  );
  await expect(page.getByRole("combobox", { name: "Grid cell" })).toBeFocused();
  await expect(page.getByRole("combobox", { name: "Table class" })).toHaveValue(
    "car_or_van",
  );
  await events.evaluate((element) => {
    (document.activeElement as HTMLElement)?.blur();
    element.scrollIntoView();
    window.scrollBy(0, -100);
  });
  await expect(events).toHaveScreenshot("experimental-alerts.png", {
    stylePath: fileURLToPath(
      new URL("./section-screenshot.css", import.meta.url),
    ),
  });
});

test("sampled video navigation follows timestamps and handles missing images", async ({
  page,
}) => {
  const result = videoResultFixture();
  result.frames.forEach((frame) => {
    frame.visual_asset = null;
    frame.output_asset_id = null;
  });
  await page.route("**/api/analyses/42", (route) =>
    route.fulfill({ json: result }),
  );
  await page.goto("/analyses/42");
  await expect(
    page.getByRole("combobox", { name: "Sampled frame" }),
  ).toHaveValue("20");
  await expect(
    page.getByRole("button", { name: "Previous sampled frame" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Next sampled frame" }).click();
  await expect(
    page.getByRole("combobox", { name: "Sampled frame" }),
  ).toHaveValue("21");
  await expect(
    page.getByText("Result image unavailable", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next sampled frame" }).click();
  await expect(
    page.getByRole("combobox", { name: "Sampled frame" }),
  ).toHaveValue("22");
  await expect(
    page.getByRole("button", { name: "Next sampled frame" }),
  ).toBeDisabled();
  await checkPageWidth(page);
});

test("unavailable service keeps mobile navigation and information accessible", async ({
  page,
}) => {
  await page.route("**/api/health", (route) => route.abort());
  await page.goto("/analyses");
  await expect(
    page.getByText("Backend unavailable", { exact: true }),
  ).toBeVisible({ timeout: 15000 });
  await checkPageWidth(page);
  await expect(page.locator("header")).toHaveScreenshot(
    "unavailable-header.png",
  );
  await page.getByRole("button", { name: "Application information" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});
