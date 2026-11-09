import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import {
  measureSubmission,
  armReadiness,
} from "../measurements/browserReadiness.ts";
import { gridResultFixture } from "../src/test/analysisResultFixture.ts";

const imagePath = fileURLToPath(
  new URL("../../data/input/sample_image.jpg", import.meta.url),
);
async function form(page: Page, zero = false, reject = false) {
  const result = gridResultFixture();
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
    url: frame.visual_asset!.url + "/source",
    rendered_overlays: [],
  };
  if (zero) {
    frame.detections = [];
    frame.frame_summaries = [];
    for (const cell of frame.grid_cells) cell.summaries = [];
  }
  await page.route("http://localhost:8000/api/**", (r) =>
    r.fulfill({
      status: 503,
      json: { error: { message: "Unexpected test request" } },
    }),
  );
  await page.route("**/api/health", (r) =>
    r.fulfill({ json: { status: "ok", service: "test", version: "1" } }),
  );
  await page.route("**/api/capabilities", (r) =>
    r.fulfill({
      json: {
        image: {
          extensions: [".jpg"],
          mime_types: ["image/jpeg"],
          mime_type_by_extension: { ".jpg": "image/jpeg" },
          max_upload_bytes: 10000000,
          max_pixels: 40000000,
        },
        video: {
          extensions: [".avi"],
          mime_types: ["video/x-msvideo"],
          mime_type_by_extension: { ".avi": "video/x-msvideo" },
          max_upload_bytes: 500000000,
          max_pixels: 40000000,
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
  await page.route("**/api/analyses/images", (r) =>
    r.fulfill({
      status: reject ? 422 : 201,
      headers: { "x-request-id": "controlled-browser-request" },
      json: reject
        ? { error: { code: "invalid_image", message: "Controlled rejection." } }
        : { session_id: 42, status: "completed" },
    }),
  );
  await page.route("**/api/analyses/42", (r) => r.fulfill({ json: result }));
  await page.goto("/workspace");
  await page.getByLabel("Choose image file").setInputFiles(imagePath);
  return result;
}
const options = {
  apiOrigin: "http://localhost:8000",
  kind: "image" as const,
  gridCells: 4,
  timeoutMs: 10000,
};

test("browser timer excludes form setup and waits for decoded result media", async ({
  page,
}) => {
  await form(page);
  await armReadiness(page, 4, 10000);
  expect(
    await page.evaluate(() => window.__readinessProbe!.started),
  ).toBeNull();
  let release!: () => void;
  let requested!: () => void;
  const imageRequested = new Promise<void>((resolve) => {
    requested = resolve;
  });
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/assets/*/source", async (route) => {
    requested();
    await gate;
    await route.fulfill({ path: imagePath, contentType: "image/jpeg" });
  });
  const pending = measureSubmission(page, options);
  await imageRequested;
  expect(await page.evaluate(() => window.__readinessProbe!.ready)).toBeNull();
  const releasedAt = await page.evaluate(() => performance.now());
  release();
  const row = await pending;
  expect(row.status).toBe("completed");
  expect(row.probe!.decoded!).toBeGreaterThanOrEqual(releasedAt);
  expect(row.probe!.ready!).toBeGreaterThan(row.probe!.decoded!);
  expect(row.browser_seconds).toBeGreaterThan(0);
  expect(row.probe!.scene!.detections).toHaveLength(3);
});

test("zero detections can be ready without inventing boxes", async ({
  page,
}) => {
  await form(page, true);
  await page.route("**/api/assets/*/source", (r) =>
    r.fulfill({ path: imagePath, contentType: "image/jpeg" }),
  );
  const row = await measureSubmission(page, options);
  expect(row.status).toBe("completed");
  expect(row.probe!.scene!.detections).toEqual([]);
});

test("missing media remains failed even after a successful API response", async ({
  page,
}) => {
  await form(page);
  await page.route("**/api/assets/*/source", (r) => r.fulfill({ status: 404 }));
  const row = await measureSubmission(page, { ...options, timeoutMs: 2000 });
  expect(row.status).toBe("failed");
  expect(row.failure_code).toBe("readiness_timeout");
  expect(row.browser_seconds).toBeNull();
  expect(row.network.some((r) => r.status === 201)).toBe(true);
  expect(row.network.some((r) => r.status === 404)).toBe(true);
});

test("misaligned overlays are not accepted as usable results", async ({
  page,
}) => {
  await form(page);
  await page.addStyleTag({
    content:
      'button[aria-label^="Detection "] { transform: translateX(30px) !important; }',
  });
  await page.route("**/api/assets/*/source", (r) =>
    r.fulfill({ path: imagePath, contentType: "image/jpeg" }),
  );
  const row = await measureSubmission(page, options);
  expect(row.status).toBe("failed");
  expect(row.failure_code).toBe("browser_or_evidence_check_failed");
  expect(row.probe!.ready).not.toBeNull();
});

test("rejected submissions are retained and never retried by the runner", async ({
  page,
}) => {
  await form(page, false, true);
  const row = await measureSubmission(page, { ...options, timeoutMs: 2000 });
  expect(row.status).toBe("failed");
  expect(row.browser_seconds).toBeNull();
  expect(
    row.network.filter((r) => r.path === "/api/analyses/images"),
  ).toHaveLength(1);
  expect(
    row.network.find((r) => r.path === "/api/analyses/images")!.status,
  ).toBe(422);
});
