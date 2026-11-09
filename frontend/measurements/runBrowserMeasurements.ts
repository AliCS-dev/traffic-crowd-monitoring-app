import { chromium, type Browser } from "@playwright/test";
import { execFileSync } from "node:child_process";
import {
  readFileSync,
  readdirSync,
  mkdirSync,
  writeFileSync,
  renameSync,
} from "node:fs";
import { dirname, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs, isDeepStrictEqual } from "node:util";
import { measureSubmission } from "./browserReadiness.ts";
import {
  digest,
  localOrigin,
  repetitions,
  checkStack,
  checkProfile,
  summaries,
  type ContainerIdentity,
} from "./evidence.ts";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontend, "..");
const { values } = parseArgs({
  options: {
    "base-url": { type: "string" },
    "backend-container": { type: "string" },
    "frontend-container": { type: "string" },
    "output-directory": { type: "string" },
    repetitions: { type: "string", default: "10" },
  },
});
for (const key of [
  "base-url",
  "backend-container",
  "frontend-container",
  "output-directory",
] as const)
  if (!values[key]) throw new Error(`Missing --${key}`);
const origin = localOrigin(values["base-url"]!);
const count = repetitions(values.repetitions);
const directory = resolve(root, values["output-directory"]!);
const command = (executable: string, args: string[]) =>
  execFileSync(executable, args, {
    cwd: root,
    encoding: "utf8",
    timeout: 30000,
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
function identity(container: string): ContainerIdentity {
  return JSON.parse(
    command("docker", [
      "inspect",
      "--format",
      '{"id":{{json .Id}},"image":{{json .Image}},"started_at":{{json .State.StartedAt}},"running":{{json .State.Running}},"service":{{json (index .Config.Labels "com.docker.compose.service")}},"project":{{json (index .Config.Labels "com.docker.compose.project")}},"measurement":{{json (index .Config.Labels "org.traffic-monitoring.measurement")}},"ports":{{json (index .NetworkSettings.Ports "8080/tcp")}}}',
      container,
    ]),
  );
}
function fileManifest(path: string): Record<string, string> {
  const result: Record<string, string> = {};
  function visit(current: string) {
    for (const entry of readdirSync(current, { withFileTypes: true }).sort(
      (a, b) => a.name.localeCompare(b.name),
    )) {
      const full = resolve(current, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.isFile())
        result[relative(path, full)] = digest(readFileSync(full));
    }
  }
  visit(path);
  return result;
}
function toolHashes() {
  return {
    ...fileManifest(resolve(frontend, "measurements")),
    scenario_file: digest(
      readFileSync(resolve(root, "configs/evaluation/system_workflows.json")),
    ),
  };
}
function sourceHashes() {
  return {
    ...fileManifest(resolve(frontend, "src")),
    ...Object.fromEntries(
      [
        "package.json",
        "package-lock.json",
        "vite.config.ts",
        "index.html",
        "Dockerfile",
        "nginx.conf",
      ].map((f) => [f, digest(readFileSync(resolve(frontend, f)))]),
    ),
  };
}
function setup() {
  return JSON.parse(
    command(resolve(root, ".venv/bin/python"), [
      "-c",
      'import json,sys; from pathlib import Path; from evaluation.system_measurement import backend_identity,load_scenarios; from app.runtime_provenance import source_identity; print(json.dumps({"runner":source_identity(Path.cwd()),"backend":backend_identity(sys.argv[1]),"scenarios":[s.model_dump() for s in load_scenarios(Path("configs/evaluation/system_workflows.json"))]}))',
      values["backend-container"]!,
    ]),
  );
}
type Attempt = Awaited<ReturnType<typeof measureSubmission>> & {
  scenario_id: string;
  viewport: string;
  phase: string;
  repetition: number;
  started_at: string;
  screenshot?: string;
  artifact_errors?: string[];
  served_files?: Record<string, string>;
};
const report: {
  schema_version: number;
  purpose: string;
  status: string;
  started_at: string;
  finished_at?: string;
  settings: unknown;
  attempts: Attempt[];
  errors: string[];
  setup?: ReturnType<typeof setup>;
  frontend_container?: ContainerIdentity;
  backend_container?: ContainerIdentity;
  frontend_source?: Record<string, string>;
  production_files?: Record<string, string>;
  tools?: Record<string, string>;
  browser_version?: string;
  node_version: string;
  summary?: ReturnType<typeof summaries>;
} = {
  schema_version: 1,
  purpose:
    "Browser readiness tooling verification; not final performance or accuracy",
  status: "in_progress",
  started_at: new Date().toISOString(),
  settings: {
    origin,
    repetitions: count,
    warmups_per_scenario_viewport: 1,
    timeout_ms: 360000,
    viewports: {
      desktop: { width: 1440, height: 1000 },
      mobile: { width: 320, height: 900 },
    },
    browser_context: "fresh per attempt; workspace loaded before timer",
    video_poll_ms: 1000,
    p95: "nearest rank ceil(0.95*n)",
    tracing: false,
  },
  attempts: [],
  errors: [],
  node_version: process.version,
};
function save() {
  writeFileSync(
    resolve(directory, "report.json.tmp"),
    JSON.stringify(report, null, 2) + "\n",
  );
  renameSync(
    resolve(directory, "report.json.tmp"),
    resolve(directory, "report.json"),
  );
}
mkdirSync(dirname(directory), { recursive: true });
mkdirSync(directory, { recursive: false });
save();
let browser: Browser | undefined;
try {
  report.setup = setup();
  report.backend_container = identity(values["backend-container"]!);
  report.frontend_container = identity(values["frontend-container"]!);
  checkStack(report.backend_container, report.frontend_container, origin);
  report.frontend_source = sourceHashes();
  report.tools = toolHashes();
  // Rebuild locally so a stale dist directory cannot certify a stale served bundle.
  execFileSync("npm", ["run", "build"], {
    cwd: frontend,
    env: { ...process.env, VITE_API_BASE_URL: "" },
    timeout: 120000,
    stdio: ["ignore", "pipe", "pipe"],
  });
  report.production_files = fileManifest(resolve(frontend, "dist"));
  browser = await chromium.launch({ headless: true });
  report.browser_version = browser.version();
  save();
  let profile: unknown = null;
  for (const [viewport, size] of Object.entries({
    desktop: { width: 1440, height: 1000 },
    mobile: { width: 320, height: 900 },
  })) {
    for (const scenario of report.setup.scenarios) {
      for (let repetition = 0; repetition <= count; repetition++) {
        const attempt: Attempt = {
          scenario_id: scenario.scenario_id,
          viewport,
          phase: repetition === 0 ? "warmup" : "measured",
          repetition,
          started_at: new Date().toISOString(),
          status: "failed",
          failure_code: null,
          probe: null,
          result: null,
          network: [],
          page_errors: [],
          browser_seconds: null,
        };
        report.attempts.push(attempt);
        save();
        const context = await browser.newContext({
          baseURL: origin,
          viewport: size,
          locale: "en-GB",
          timezoneId: "UTC",
          reducedMotion: "reduce",
        });
        const page = await context.newPage();
        page.setDefaultTimeout(15000);
        const checks: Promise<void>[] = [];
        const served: Record<string, string> = {};
        const artifactErrors: string[] = [];
        page.on("response", (response) => {
          const url = new URL(response.url());
          if (url.origin !== origin) artifactErrors.push("unexpected_origin");
          if (
            url.pathname === "/workspace" ||
            url.pathname.startsWith("/assets/")
          ) {
            const name =
              url.pathname === "/workspace"
                ? "index.html"
                : url.pathname.slice(1);
            checks.push(
              (async () => {
                const hash = digest(await response.body());
                served[name] = hash;
                if (!response.ok() || report.production_files![name] !== hash)
                  artifactErrors.push("served_bundle_mismatch");
              })().catch(() => {
                artifactErrors.push("served_bundle_unavailable");
              }),
            );
          }
        });
        try {
          await page.goto("/workspace");
          if (scenario.kind === "video")
            await page
              .getByRole("button", { name: "Video", exact: true })
              .click();
          const bytes = readFileSync(resolve(root, scenario.path));
          if (digest(bytes) !== scenario.sha256)
            throw new Error("input_changed");
          const mime =
            scenario.kind === "video" ? "video/x-msvideo" : "image/png";
          // Current scenarios are the three fixed PNG/AVI fixtures, not arbitrary media.
          if (
            !scenario.path.endsWith(scenario.kind === "video" ? ".avi" : ".png")
          )
            throw new Error("unsupported_measurement_fixture");
          await page.getByLabel(`Choose ${scenario.kind} file`).setInputFiles({
            name: scenario.path.split("/").at(-1),
            mimeType: mime,
            buffer: bytes,
          });
          await page
            .getByLabel("Session name")
            .fill(`browser-${scenario.scenario_id}-${viewport}-${repetition}`);
          if (scenario.grid_rows) {
            await page
              .getByRole("switch", { name: "Divide the scene into a grid" })
              .check();
            await page
              .getByLabel("Grid rows", { exact: true })
              .fill(String(scenario.grid_rows));
            await page
              .getByLabel("Grid columns", { exact: true })
              .fill(String(scenario.grid_columns));
          }
          if (scenario.kind === "video")
            await page
              .getByLabel("Sampling interval")
              .fill(String(scenario.sampling_interval_seconds));
          Object.assign(
            attempt,
            await measureSubmission(page, {
              apiOrigin: origin,
              kind: scenario.kind,
              gridCells:
                (scenario.grid_rows ?? 0) * (scenario.grid_columns ?? 0),
              timeoutMs: 360000,
            }),
          );
          if (attempt.status === "completed") {
            profile = checkProfile(
              attempt.result!,
              report.setup.backend,
              profile,
            );
            await page
              .getByRole("group", { name: "Scene viewport", exact: true })
              .scrollIntoViewIfNeeded();
          }
          const screenshot = `${scenario.scenario_id}-${viewport}-${repetition}.png`;
          await page.screenshot({ path: resolve(directory, screenshot) });
          attempt.screenshot = screenshot;
          let checked = 0;
          while (checked < checks.length) {
            const batch = checks.slice(checked);
            checked = checks.length;
            await Promise.all(batch);
          }
          if (!served["index.html"] || Object.keys(served).length < 2)
            artifactErrors.push("missing_served_bundle_evidence");
          attempt.served_files = served;
          attempt.artifact_errors = artifactErrors;
          if (artifactErrors.length)
            throw new Error("served_bundle_check_failed");
          if (attempt.status !== "completed")
            throw new Error("browser_attempt_failed");
        } catch {
          attempt.status = "failed";
          attempt.failure_code ||= "browser_or_provenance_check_failed";
          if (!attempt.screenshot) {
            const screenshot = `${scenario.scenario_id}-${viewport}-${repetition}-failed.png`;
            await page
              .screenshot({ path: resolve(directory, screenshot) })
              .then(() => {
                attempt.screenshot = screenshot;
              })
              .catch(() => {});
          }
          throw new Error("attempt_failed_no_retry");
        } finally {
          await Promise.all(checks);
          attempt.served_files = served;
          attempt.artifact_errors = artifactErrors;
          await context.close();
          save();
        }
      }
    }
  }
  if (
    !isDeepStrictEqual(setup(), report.setup) ||
    !isDeepStrictEqual(
      identity(values["frontend-container"]!),
      report.frontend_container,
    ) ||
    !isDeepStrictEqual(
      identity(values["backend-container"]!),
      report.backend_container,
    ) ||
    !isDeepStrictEqual(sourceHashes(), report.frontend_source) ||
    !isDeepStrictEqual(toolHashes(), report.tools)
  )
    throw new Error("run_inputs_changed");
  report.status = "recorded";
} catch {
  report.errors.push("run_incomplete_check_attempts_and_prerequisites");
  report.status = "incomplete";
} finally {
  await browser?.close();
  report.summary = summaries(report.attempts);
  report.finished_at = new Date().toISOString();
  save();
  const rows = [
    [
      "scenario",
      "viewport",
      "phase",
      "repetition",
      "status",
      "seconds",
      "failure_code",
    ],
    ...report.attempts.map((a) => [
      a.scenario_id,
      a.viewport,
      a.phase,
      a.repetition,
      a.status,
      a.browser_seconds,
      a.failure_code,
    ]),
  ];
  writeFileSync(
    resolve(directory, "attempts.csv"),
    rows
      .map((r) => r.map((v) => JSON.stringify(String(v ?? ""))).join(","))
      .join("\n") + "\n",
  );
  const files = [
    "report.json",
    "attempts.csv",
    ...report.attempts.flatMap((a) => (a.screenshot ? [a.screenshot] : [])),
  ];
  writeFileSync(
    resolve(directory, "sha256.json"),
    JSON.stringify(
      Object.fromEntries(
        files.map((f) => [f, digest(readFileSync(resolve(directory, f)))]),
      ),
      null,
      2,
    ) + "\n",
  );
}
console.log(
  JSON.stringify({
    status: report.status,
    attempts: report.attempts.length,
    report: resolve(directory, "report.json"),
  }),
);
if (report.status !== "recorded") process.exitCode = 1;
