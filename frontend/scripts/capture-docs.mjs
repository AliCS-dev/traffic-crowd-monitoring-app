import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";

const baseURL = process.env.DOCS_BASE_URL ?? "http://localhost:8081";
const origin = new URL(baseURL);
if (!["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname)) {
  throw new Error("Documentation capture is restricted to a local demo stack.");
}
const output = new URL("../../docs/images/user-guide/", import.meta.url);
const fixture = new URL(
  "../../data/runtime-regression/fixtures/roundabout_6.png",
  import.meta.url,
);
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
try {
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
    locale: "en-GB",
    timezoneId: "Europe/Budapest",
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const ready = await context.request.get("/api/ready");
  expect(ready.status()).toBe(200);
  expect((await ready.json()).status).toBe("ready");

  const screenshots = {};
  async function capture(name, options = {}) {
    await page.evaluate(() => document.fonts.ready);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const bytes = await page.screenshot({
      path: fileURLToPath(new URL(name, output)),
      animations: "disabled",
      ...options,
    });
    screenshots[name] = sha256(bytes);
  }

  await page.goto("/workspace");
  await page
    .getByLabel("Choose image file")
    .setInputFiles(fileURLToPath(fixture));
  await page
    .getByLabel("Session name")
    .fill("Documentation - roundabout image");
  await page
    .getByRole("switch", { name: "Divide the scene into a grid" })
    .check();
  await page.getByLabel("Grid rows", { exact: true }).fill("2");
  await page.getByLabel("Grid columns", { exact: true }).fill("3");
  await capture("workspace.png");

  let sessionId = process.env.DOCS_SESSION_ID;
  if (sessionId) {
    if (!/^\d+$/.test(sessionId)) throw new Error("Invalid DOCS_SESSION_ID");
    await page.goto(`/analyses/${sessionId}`);
  } else {
    await page.getByRole("button", { name: "Start analysis" }).click();
    await expect(page).toHaveURL(/\/analyses\/\d+$/, { timeout: 180_000 });
    sessionId = new URL(page.url()).pathname.split("/").at(-1);
    console.log(`Created documentation session ${sessionId}`);
  }
  const response = await context.request.get(`/api/analyses/${sessionId}`);
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.status).toBe("completed");
  expect(result.sources).toHaveLength(1);
  expect(result.sources[0].original_filename).toBe("roundabout_6.png");
  expect(result.frames).toHaveLength(1);
  const frame = result.frames[0];
  expect(frame.grid_cells).toHaveLength(6);
  expect(
    frame.frame_summaries.reduce((sum, row) => sum + row.object_count, 0),
  ).toBe(frame.detections.length);
  expect(
    frame.grid_cells
      .flatMap((cell) => cell.summaries)
      .reduce((sum, row) => sum + row.object_count, 0),
  ).toBe(frame.detections.length);
  expect(result.model_profile.quality_gate_status).toBe("failed");
  expect(result.dense_crowd_analysis.status).toBe("unsupported");
  expect(result.dense_crowd_analysis.count).toBeNull();

  const image = page.getByRole("img", { name: /^Detection result for / });
  await expect(image).toBeVisible();
  await expect(image).toHaveJSProperty("complete", true);
  expect(
    await image.evaluate((element) => element.naturalWidth),
  ).toBeGreaterThan(0);
  const cell =
    frame.grid_cells.find((item) => item.summaries.length) ??
    frame.grid_cells[0];
  await page
    .getByLabel("Grid cell", { exact: true })
    .selectOption(String(cell.id));
  await page
    .getByRole("region", { name: "Image result", exact: true })
    .evaluate((element) =>
      window.scrollTo(
        0,
        element.getBoundingClientRect().top + window.scrollY - 75,
      ),
    );
  await capture("image-result.png");

  await page
    .getByRole("heading", { name: "Dense-crowd analysis", exact: true })
    .evaluate((element) =>
      window.scrollTo(
        0,
        element.getBoundingClientRect().top + window.scrollY - 100,
      ),
    );
  const crowdBounds = await page
    .getByRole("region", { name: "Dense-crowd analysis", exact: true })
    .boundingBox();
  const modelBounds = await page
    .getByRole("region", { name: "Model used for this analysis", exact: true })
    .boundingBox();
  await capture("model-status.png", {
    clip: {
      x: crowdBounds.x,
      y: crowdBounds.y,
      width: crowdBounds.width,
      height: modelBounds.y + modelBounds.height - crowdBounds.y,
    },
  });

  await page.goto("/sessions");
  await expect(page.locator(`a[href="/analyses/${sessionId}"]`)).toBeVisible();
  await capture("session-history.png");
  await page.locator(`a[href="/analyses/${sessionId}"]`).click();
  await expect(image).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: fileURLToPath(
      new URL("../test-results/docs-mobile.png", import.meta.url),
    ),
    fullPage: true,
  });
  expect(errors).toEqual([]);

  const asset = await context.request.get(frame.visual_asset.url);
  expect(asset.status()).toBe(200);
  const record = {
    captured_at: new Date().toISOString(),
    purpose: "Live image workflow illustration, not an accuracy benchmark",
    api_mocked: false,
    viewport: { width: 1440, height: 1000 },
    browser: `Chromium ${browser.version()}`,
    input: "data/runtime-regression/fixtures/roundabout_6.png",
    input_sha256: sha256(await readFile(fixture)),
    session_id: result.id,
    model_id: result.model_profile.model_id,
    checkpoint_sha256: result.model_profile.checkpoint_sha256,
    application_commit:
      result.model_profile.runtime_provenance?.application_commit,
    backend_source_sha256:
      result.model_profile.runtime_provenance?.source_sha256,
    quality_gate_status: result.model_profile.quality_gate_status,
    dense_crowd_status: result.dense_crowd_analysis.status,
    device: result.model_profile.device,
    detections: frame.detections.length,
    grid_cells: frame.grid_cells.length,
    selected_cell: {
      row_index: cell.row_index,
      column_index: cell.column_index,
    },
    result_asset_sha256: sha256(await asset.body()),
    checks: [
      "image decoded",
      "frame and grid totals match detections",
      "saved result reopened",
      "no desktop or 390px overflow",
      "no browser page errors",
    ],
    screenshots,
  };
  await writeFile(
    new URL("capture.json", output),
    JSON.stringify(record, null, 2) + "\n",
  );
  console.log(JSON.stringify(record, null, 2));
} finally {
  await browser.close();
}
