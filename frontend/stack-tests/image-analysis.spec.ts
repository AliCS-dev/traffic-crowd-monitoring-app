import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import type { MonitoringSessionResult } from "../src/api/analysisResults.ts";

test("real image workflow through the Compose frontend", async ({
  page,
  request,
  baseURL,
}, testInfo) => {
  const pageErrors: string[] = [];
  const externalApiRequests: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (
      url.pathname.startsWith("/api/") &&
      url.origin !== new URL(baseURL!).origin
    ) {
      externalApiRequests.push(req.url());
    }
  });
  const ready = await request.get("/api/ready");
  expect(ready.status()).toBe(200);
  expect((await ready.json()).status).toBe("ready");

  let sessionId = process.env.STACK_SESSION_ID;
  if (!sessionId) {
    if (!process.env.STACK_IMAGE) {
      throw new Error("Set STACK_IMAGE to a local JPG/PNG for this live test.");
    }
    await page.goto("/workspace");
    await page
      .getByLabel("Choose image file")
      .setInputFiles(resolve(process.env.STACK_IMAGE));
    await page
      .getByLabel("Session name")
      .fill(`compose-${testInfo.project.name}-${Date.now()}`);
    const grid = page.getByRole("switch", {
      name: "Divide the scene into a grid",
    });
    await grid.check();
    await page.getByLabel("Grid rows", { exact: true }).fill("2");
    await page.getByLabel("Grid columns", { exact: true }).fill("3");
    await page.getByRole("button", { name: "Start analysis" }).click();
    await expect(page).toHaveURL(/\/analyses\/\d+$/, { timeout: 150_000 });
    sessionId = new URL(page.url()).pathname.split("/").at(-1)!;
  } else {
    await page.goto(`/analyses/${sessionId}`);
  }

  const response = await request.get(`/api/analyses/${sessionId}`);
  expect(response.status()).toBe(200);
  const result = (await response.json()) as MonitoringSessionResult;
  expect(result.status).toBe("completed");
  expect(result.frames).toHaveLength(1);
  const frame = result.frames[0];
  expect(frame.grid_cells).toHaveLength(6);
  expect(
    frame.frame_summaries.reduce((sum, row) => sum + row.object_count, 0),
  ).toBe(frame.detections.length);
  expect(result.model_profile?.device).toBe(
    process.env.STACK_EXPECTED_DEVICE ?? "cuda:0",
  );
  expect(result.model_profile?.quality_gate_status).toBe("failed");
  expect(result.dense_crowd_analysis?.status).toBe("unsupported");
  expect(result.dense_crowd_analysis?.count).toBeNull();
  expect(result.model_profile?.runtime_provenance?.schema_version).toBe(1);
  expect(
    result.model_profile?.runtime_provenance?.dependencies.ultralytics,
  ).toBeTruthy();
  await page.getByText("Runtime environment", { exact: true }).click();
  await expect(
    page.getByText("Backend source SHA-256", { exact: true }),
  ).toBeVisible();
  await page.getByText("Dependencies", { exact: true }).click();
  await expect(page.getByText("ultralytics", { exact: true })).toBeVisible();

  const image = page.getByRole("img", { name: /^Detection result for / });
  await expect(image).toBeVisible();
  expect(
    await image.evaluate(
      (element: HTMLImageElement) =>
        element.complete && element.naturalWidth > 0,
    ),
  ).toBe(true);
  await expect(page.getByRole("group", { name: "Image grid" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const asset = await request.get(frame.visual_asset!.url);
  expect(asset.status()).toBe(200);
  expect(asset.headers()["content-type"]).toContain("image/jpeg");
  const assetSha256 = createHash("sha256")
    .update(await asset.body())
    .digest("hex");
  if (process.env.STACK_EXPECTED_ASSET_SHA256) {
    expect(assetSha256).toBe(process.env.STACK_EXPECTED_ASSET_SHA256);
  }
  await page.screenshot({
    path: testInfo.outputPath("compose-result.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(image).toBeVisible();
  await page.goto("/sessions");
  await expect(
    page.getByText(result.session_name!, { exact: true }),
  ).toBeVisible();
  expect(pageErrors).toEqual([]);
  expect(externalApiRequests).toEqual([]);
  const evidence = {
    sessionId: result.id,
    device: result.model_profile?.device,
    checkpointSha256: result.model_profile?.checkpoint_sha256,
    detections: frame.detections.length,
    gridCells: frame.grid_cells.length,
    assetSha256,
    purpose: "Live workflow check, not a model-accuracy benchmark",
  };
  await testInfo.attach("workflow-evidence", {
    body: JSON.stringify(evidence, null, 2),
    contentType: "application/json",
  });
  console.log(JSON.stringify(evidence));
});
