import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import {
  analysisResultFixture,
  videoResultFixture,
} from "../src/test/analysisResultFixture.ts";

const fixtures = fileURLToPath(
  new URL("../../data/runtime-regression/fixtures/", import.meta.url),
);

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => {
    throw error;
  });
  await page.route("http://localhost:8000/api/**", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { message: "Unexpected request" } },
    }),
  );
  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: { status: "ok", service: "Controlled API", version: "1" },
    }),
  );
  await page.route("**/api/capabilities", (route) =>
    route.fulfill({
      json: {
        image: {
          extensions: [".png"],
          mime_types: ["image/png"],
          mime_type_by_extension: { ".png": "image/png" },
          max_upload_bytes: 10 * 1024 * 1024,
          max_pixels: 40_000_000,
        },
        video: {
          extensions: [".avi"],
          mime_types: ["video/x-msvideo"],
          mime_type_by_extension: { ".avi": "video/x-msvideo" },
          max_upload_bytes: 500 * 1024 * 1024,
          max_pixels: 40_000_000,
        },
        options: {
          max_session_name_length: 150,
          max_grid_dimension: 20,
          default_sampling_interval_seconds: 1,
          min_sampling_interval_seconds: 0.25,
          max_sampling_interval_seconds: 3600,
          max_video_duration_seconds: 300,
          max_video_source_frames: 36000,
          max_sampled_frames: 300,
          max_processed_pixels: 40000000,
          max_inflight_analyses: 3,
        },
      },
    }),
  );
  await page.route("**/api/assets/*", (route) =>
    route.fulfill({
      path: `${fixtures}/roundabout_6.png`,
      contentType: "image/png",
    }),
  );
});

test("image submission opens its saved result and history link", async ({
  page,
}) => {
  const result = analysisResultFixture();
  await page.route("**/api/analyses/images", async (route) => {
    expect(route.request().method()).toBe("POST");
    const body = route.request().postDataBuffer()!.toString();
    expect(body).toContain('filename="roundabout_6.png"');
    expect(body).toContain("Browser image check");
    await route.fulfill({
      status: 201,
      json: { session_id: 42, status: "completed" },
    });
  });
  await page.route("**/api/analyses/42", (route) =>
    route.fulfill({ json: result }),
  );
  await page.route("**/api/analyses?*", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            id: 42,
            session_name: "Browser image check",
            status: "completed",
            started_at: result.started_at,
            completed_at: result.completed_at,
          },
        ],
        pagination: { page: 1, page_size: 20, total_items: 1, total_pages: 1 },
      },
    }),
  );
  await page.goto("/workspace");
  await page
    .getByLabel("Choose image file")
    .setInputFiles(`${fixtures}/roundabout_6.png`);
  await page.getByLabel("Session name").fill("Browser image check");
  await page.getByRole("button", { name: "Start analysis" }).click();
  await expect(page).toHaveURL(/\/analyses\/42$/);
  await expect(
    page.getByRole("img", { name: /^Detection result for / }),
  ).toBeVisible();
  await page.goto("/sessions");
  await page.locator('a[href="/analyses/42"]').click();
  await expect(page).toHaveURL(/\/analyses\/42$/);
});

for (const outcome of ["completed", "failed"] as const) {
  test(`video upload shows progress and ${outcome} state`, async ({ page }) => {
    let polls = 0;
    let allowCompletion = false;
    await page.route("**/api/analyses/videos", async (route) => {
      expect(route.request().method()).toBe("POST");
      const body = route.request().postDataBuffer()!.toString();
      expect(body).toContain('filename="roundabout_sequence.avi"');
      expect(body).toContain("Content-Type: video/x-msvideo");
      await route.fulfill({
        status: 202,
        json: { session_id: 42, status: "queued", sampled_frames_total: 3 },
      });
    });
    await page.route("**/api/analyses/videos/42", (route) => {
      polls += 1;
      return route.fulfill({
        json: {
          session_id: 42,
          status: allowCompletion ? outcome : "processing",
          sampled_frames_total: 3,
          sampled_frames_processed: allowCompletion ? 3 : 1,
          progress_percent: allowCompletion ? 100 : 33,
          failure_code: outcome === "failed" ? "video_processing_failed" : null,
          failure_message:
            outcome === "failed" ? "Controlled processing failure." : null,
        },
      });
    });
    await page.route("**/api/analyses/42", (route) =>
      route.fulfill({ json: videoResultFixture() }),
    );
    await page.goto("/workspace");
    await page.getByRole("button", { name: "Video", exact: true }).click();
    // Native file-path MIME inference differs between Linux runners.
    await page.getByLabel("Choose video file").setInputFiles({
      name: "roundabout_sequence.avi",
      mimeType: "video/x-msvideo",
      buffer: await readFile(`${fixtures}/roundabout_sequence.avi`),
    });
    await page.getByRole("button", { name: "Start analysis" }).click();
    await expect(
      page.getByText("Processing video", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("progressbar", { name: "Video processing progress" }),
    ).toHaveAttribute("aria-valuenow", "33");
    allowCompletion = true;
    if (outcome === "completed") {
      await expect(page).toHaveURL(/\/analyses\/42$/);
      await expect(
        page.getByRole("combobox", { name: "Sampled frame" }),
      ).toBeVisible();
    } else {
      await expect(
        page.getByText("Analysis failed", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("Controlled processing failure."),
      ).toBeVisible();
      await expect(page).toHaveURL(/\/workspace$/);
      await expect(
        page.getByRole("button", { name: "Start analysis" }),
      ).toBeEnabled();
    }
    expect(polls).toBeGreaterThanOrEqual(2);
  });
}

test("video with mismatched MIME metadata is rejected before submission", async ({
  page,
}) => {
  const submissions: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().endsWith("/api/analyses/videos")
    ) {
      submissions.push(request.url());
    }
  });
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Video", exact: true }).click();
  await page.getByLabel("Choose video file").setInputFiles({
    name: "roundabout_sequence.avi",
    mimeType: "image/png",
    buffer: await readFile(`${fixtures}/roundabout_sequence.avi`),
  });
  await page.getByRole("button", { name: "Start analysis" }).click();
  await expect(
    page.getByText(
      "The selected file type does not match a supported video format.",
    ),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/workspace$/);
  expect(submissions).toEqual([]);
});

test("rejected image keeps the selected file and does not open a result", async ({
  page,
}) => {
  let submissions = 0;
  await page.route("**/api/analyses/images", (route) => {
    submissions += 1;
    expect(route.request().postDataBuffer()!.toString()).toContain(
      'filename="roundabout_6.png"',
    );
    return route.fulfill({
      status: 422,
      json: {
        error: {
          code: "invalid_image",
          message: "The uploaded image could not be decoded.",
        },
      },
    });
  });
  await page.goto("/workspace");
  await page
    .getByLabel("Choose image file")
    .setInputFiles(`${fixtures}/roundabout_6.png`);
  await page.getByRole("button", { name: "Start analysis" }).click();
  await expect(
    page.getByText("Analysis failed", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("The uploaded image could not be decoded."),
  ).toBeVisible();
  await expect(
    page.getByText("roundabout_6.png", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Start analysis" }).click();
  await expect.poll(() => submissions).toBe(2);
  await expect(page).toHaveURL(/\/workspace$/);
});
