import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import type { MonitoringSessionResult } from "../src/api/analysisResults.ts";

test("saved video samples serve clean media and synchronized overlays", async ({
  page,
  request,
}, testInfo) => {
  const fixture = fileURLToPath(
    new URL(
      "../../data/runtime-regression/fixtures/roundabout_sequence.avi",
      import.meta.url,
    ),
  );
  const response = await request.post("/api/analyses/videos", {
    multipart: {
      video: {
        name: "roundabout_sequence.avi",
        mimeType: "video/x-msvideo",
        buffer: await readFile(fixture),
      },
      session_name: `scene-video-${testInfo.project.name}`,
      sampling_interval_seconds: "1",
      grid_rows: "2",
      grid_columns: "3",
    },
  });
  expect(response.status()).toBe(202);
  const created = await response.json();
  await expect
    .poll(
      async () => {
        const status = await request.get(
          `/api/analyses/videos/${created.session_id}`,
        );
        return (await status.json()).status;
      },
      { timeout: 150_000, intervals: [1000, 2000] },
    )
    .toBe("completed");
  const result = (await (
    await request.get(`/api/analyses/${created.session_id}`)
  ).json()) as MonitoringSessionResult;
  expect(result.frames).toHaveLength(3);
  for (const frame of result.frames) {
    expect(frame.source_asset?.rendered_overlays).toEqual([]);
    expect((await request.get(frame.source_asset!.url)).status()).toBe(200);
    expect((await request.get(frame.visual_asset!.url)).status()).toBe(200);
  }
  await page.goto(`/analyses/${result.id}`);
  for (let index = 0; index < result.frames.length; index++) {
    const frame = result.frames[index];
    const image = page.getByRole("img", { name: /^Detection result for / });
    await expect(image).toHaveAttribute("src", frame.source_asset!.url);
    await expect(
      page
        .getByRole("group", { name: "Detection overlays" })
        .getByRole("button"),
    ).toHaveCount(frame.detections.length);
    await page.getByRole("button", { name: "Zoom in", exact: true }).click();
    if (index < result.frames.length - 1) {
      await page.getByRole("button", { name: "Next sampled frame" }).click();
      await expect(page.getByText("100%", { exact: true })).toBeVisible();
    }
  }
  await expect(
    page.getByRole("button", { name: "Next sampled frame" }),
  ).toBeDisabled();
  console.log(
    JSON.stringify({
      sessionId: result.id,
      samples: result.frames.length,
      counts: result.frames.map((frame) => frame.detections.length),
      purpose: "Saved video scene workflow, not accuracy evaluation",
    }),
  );
});
