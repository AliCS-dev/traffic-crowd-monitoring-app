import { expect, type Page, type Response } from "@playwright/test";
import type { MonitoringSessionResult } from "../src/api/analysisResults.ts";
import { orderedVideoFrames } from "../src/features/results/frameNavigation.ts";

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}
interface Scene {
  url: string;
  image: Rect;
  naturalWidth: number;
  naturalHeight: number;
  inViewport: boolean;
  detections: { id: number; rect: Rect }[];
  cells: { label: string; rect: Rect }[];
}
interface Probe {
  started: number | null;
  decoded: number | null;
  ready: number | null;
  ended: number | null;
  failure: string | null;
  scene: Scene | null;
}
declare global {
  interface Window {
    __readinessProbe?: Probe;
    __stopReadinessProbe?: () => void;
  }
}

export async function armReadiness(
  page: Page,
  gridCells: number,
  timeoutMs: number,
) {
  await page.evaluate(
    ({ gridCells, timeoutMs }) => {
      window.__stopReadinessProbe?.();
      const probe: Probe = {
        started: null,
        decoded: null,
        ready: null,
        ended: null,
        failure: null,
        scene: null,
      };
      window.__readinessProbe = probe;
      let frame = 0;
      let deadline: ReturnType<typeof setTimeout>;
      let stopped = false;
      let decodedImage: HTMLImageElement | null = null;
      let previous = "";
      const rect = (element: Element): Rect => {
        const { x, y, width, height } = element.getBoundingClientRect();
        return { x, y, width, height };
      };
      const visible = (element: Element | null): element is Element =>
        !!element &&
        element.checkVisibility({
          checkOpacity: true,
          checkVisibilityCSS: true,
        }) &&
        element.getBoundingClientRect().width > 0 &&
        element.getBoundingClientRect().height > 0;
      function stop() {
        if (!stopped && probe.started !== null) probe.ended = performance.now();
        stopped = true;
        cancelAnimationFrame(frame);
        clearTimeout(deadline);
        document.removeEventListener("click", click, true);
        document.removeEventListener("visibilitychange", visibility);
      }
      function visibility() {
        if (document.hidden) {
          probe.failure = "document_hidden";
          stop();
        }
      }
      async function sample() {
        if (stopped) return;
        const image = document.querySelector<HTMLImageElement>(
          "[data-scene-stage] img",
        );
        const stage = image?.parentElement;
        const boxes = stage?.querySelector('[aria-label="Detection overlays"]');
        const grid = stage?.querySelector('[aria-label="Image grid"]');
        if (
          image &&
          image.complete &&
          image.naturalWidth > 0 &&
          visible(image) &&
          visible(boxes ?? null) &&
          Array.from(boxes!.querySelectorAll("button")).every(visible) &&
          Array.from(grid?.querySelectorAll("button") ?? []).every(visible) &&
          (!gridCells || visible(grid ?? null))
        ) {
          if (decodedImage !== image) {
            try {
              await image.decode();
            } catch {
              probe.failure = "image_decode_failed";
              stop();
              return;
            }
            if (stopped) return;
            decodedImage = image;
            probe.decoded = performance.now();
          }
          const scene: Scene = {
            url: image.currentSrc,
            image: rect(image),
            naturalWidth: image.naturalWidth,
            naturalHeight: image.naturalHeight,
            inViewport: false,
            detections: Array.from(boxes!.querySelectorAll("button")).map(
              (button) => ({
                id: Number(
                  button
                    .getAttribute("aria-label")
                    ?.match(/^Detection (\d+):/)?.[1],
                ),
                rect: rect(button),
              }),
            ),
            cells: Array.from(grid?.querySelectorAll("button") ?? []).map(
              (button) => ({
                label: button.getAttribute("aria-label") ?? "",
                rect: rect(button),
              }),
            ),
          };
          scene.inViewport =
            scene.image.x >= 0 &&
            scene.image.y >= 0 &&
            scene.image.x + scene.image.width <= innerWidth &&
            scene.image.y + scene.image.height <= innerHeight;
          const signature = JSON.stringify(scene);
          if (scene.cells.length === gridCells && signature === previous) {
            probe.scene = scene;
            probe.ready = performance.now();
            stop();
            return;
          }
          previous = signature;
        } else previous = "";
        frame = requestAnimationFrame(sample);
      }
      function click(event: MouseEvent) {
        const button = (event.target as Element)?.closest("button");
        if (button?.textContent?.trim() !== "Start analysis") return;
        document.removeEventListener("click", click, true);
        probe.started = performance.now();
        if (document.hidden) {
          visibility();
          return;
        }
        deadline = setTimeout(() => {
          probe.failure = "readiness_timeout";
          stop();
        }, timeoutMs);
        frame = requestAnimationFrame(sample);
      }
      document.addEventListener("click", click, true);
      document.addEventListener("visibilitychange", visibility);
      window.__stopReadinessProbe = stop;
    },
    { gridCells, timeoutMs },
  );
}

export async function readReadiness(page: Page, timeoutMs: number) {
  await page.waitForFunction(
    () =>
      (window.__readinessProbe?.ready !== null &&
        window.__readinessProbe?.ready !== undefined) ||
      !!window.__readinessProbe?.failure,
    undefined,
    { timeout: timeoutMs + 5000 },
  );
  return page.evaluate(() => window.__readinessProbe!);
}

function aligned(actual: Rect, expected: Rect) {
  for (const key of ["x", "y", "width", "height"] as const) {
    expect(Math.abs(actual[key] - expected[key])).toBeLessThan(1);
  }
}

export function validateScene(
  scene: Scene,
  result: MonitoringSessionResult,
  kind: "image" | "video",
  origin: string,
) {
  expect(result.status).toBe("completed");
  const frame =
    kind === "video" ? orderedVideoFrames(result.frames)[0] : result.frames[0];
  const asset = frame.source_asset!;
  expect(asset.rendered_overlays).toEqual([]);
  expect(scene.url).toBe(new URL(asset.url, origin).href);
  expect(scene.naturalWidth).toBe(asset.width);
  expect(scene.naturalHeight).toBe(asset.height);
  expect(scene.detections.map((b) => b.id).sort((a, b) => a - b)).toEqual(
    frame.detections.map((b) => b.id).sort((a, b) => a - b),
  );
  expect(scene.cells).toHaveLength(frame.grid_cells.length);
  const expectedRect = (bounds: {
    x_min: number;
    y_min: number;
    x_max: number;
    y_max: number;
  }): Rect => ({
    x: scene.image.x + (scene.image.width * bounds.x_min) / asset.width,
    y: scene.image.y + (scene.image.height * bounds.y_min) / asset.height,
    width: (scene.image.width * (bounds.x_max - bounds.x_min)) / asset.width,
    height: (scene.image.height * (bounds.y_max - bounds.y_min)) / asset.height,
  });
  for (const box of scene.detections)
    aligned(
      box.rect,
      expectedRect(frame.detections.find((d) => d.id === box.id)!.bounds),
    );
  for (const cell of frame.grid_cells) {
    const actual = scene.cells.find(
      (c) =>
        c.label ===
        `Row ${cell.row_index + 1}, column ${cell.column_index + 1}`,
    );
    expect(actual).toBeDefined();
    aligned(actual!.rect, expectedRect(cell.bounds));
  }
}

export async function measureSubmission(
  page: Page,
  options: {
    apiOrigin: string;
    kind: "image" | "video";
    gridCells: number;
    timeoutMs: number;
  },
) {
  const network: { path: string; status: number; request_id: string | null }[] =
    [];
  const pageErrors: string[] = [];
  const observe = (response: Response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/")) {
      if (url.origin !== new URL(options.apiOrigin).origin)
        pageErrors.push("unexpected_api_origin");
      network.push({
        path: url.pathname,
        status: response.status(),
        request_id: response.headers()["x-request-id"] ?? null,
      });
    }
  };
  const pageError = () => pageErrors.push("page_error");
  page.on("response", observe);
  page.on("pageerror", pageError);
  const attempt: {
    status: "completed" | "failed";
    failure_code: string | null;
    probe: Probe | null;
    result: MonitoringSessionResult | null;
    network: typeof network;
    page_errors: string[];
    browser_seconds: number | null;
  } = {
    status: "failed",
    failure_code: null,
    probe: null,
    result: null,
    network,
    page_errors: pageErrors,
    browser_seconds: null,
  };
  try {
    await armReadiness(page, options.gridCells, options.timeoutMs);
    await page
      .getByRole("button", { name: "Start analysis", exact: true })
      .click({ timeout: 15000 });
    const probe = await readReadiness(page, options.timeoutMs);
    attempt.probe = probe;
    if (
      probe.failure ||
      probe.started === null ||
      probe.ready === null ||
      !probe.scene
    ) {
      attempt.failure_code = probe.failure ?? "missing_browser_clock";
      return attempt;
    }
    attempt.browser_seconds = (probe.ready - probe.started) / 1000;
    expect(pageErrors).toEqual([]);
    const match = new URL(page.url()).pathname.match(/^\/analyses\/(\d+)$/);
    expect(match).not.toBeNull();
    const response = await page.evaluate(async (url) => {
      const saved = await fetch(url, { signal: AbortSignal.timeout(15000) });
      return { ok: saved.ok, body: await saved.json() };
    }, `${options.apiOrigin}/api/analyses/${match![1]}`);
    expect(response.ok).toBe(true);
    const result = response.body as MonitoringSessionResult;
    attempt.result = result;
    expect(result.id).toBe(Number(match![1]));
    validateScene(probe.scene, result, options.kind, options.apiOrigin);
    const post = network.filter(
      (r) => r.path === `/api/analyses/${options.kind}s`,
    );
    expect(post).toHaveLength(1);
    expect(post[0].status).toBe(options.kind === "image" ? 201 : 202);
    expect(post[0].request_id).toBeTruthy();
    attempt.status = "completed";
  } catch {
    attempt.failure_code = "browser_or_evidence_check_failed";
  } finally {
    if (!page.isClosed()) {
      attempt.probe = await page
        .evaluate(() => {
          window.__stopReadinessProbe?.();
          return window.__readinessProbe ?? null;
        })
        .catch(() => attempt.probe);
    }
    page.off("response", observe);
    page.off("pageerror", pageError);
  }
  return attempt;
}
