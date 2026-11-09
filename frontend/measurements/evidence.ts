import { createHash } from "node:crypto";
import { isDeepStrictEqual } from "node:util";
import type { MonitoringSessionResult } from "../src/api/analysisResults.ts";

export const digest = (bytes: string | Buffer) =>
  createHash("sha256").update(bytes).digest("hex");
export function localOrigin(value: string) {
  const url = new URL(value);
  if (
    url.protocol !== "http:" ||
    !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  )
    throw new Error("invalid_local_origin");
  return url.origin;
}
export function repetitions(value: string) {
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 30)
    throw new Error("invalid_repetitions");
  return Number(value);
}
export interface ContainerIdentity {
  id: string;
  image: string;
  started_at: string;
  running: boolean;
  service: string;
  project: string;
  measurement: string | null;
  ports: { HostIp: string; HostPort: string }[] | null;
}
export function checkStack(
  backend: ContainerIdentity,
  frontend: ContainerIdentity,
  origin: string,
) {
  if (
    !backend.running ||
    !frontend.running ||
    backend.service !== "backend" ||
    frontend.service !== "frontend" ||
    backend.measurement !== "disposable" ||
    !backend.project ||
    backend.project !== frontend.project
  )
    throw new Error("stack_not_disposable_or_mismatched");
  const port = new URL(origin).port || "80";
  if (
    !frontend.ports?.some(
      (p) => p.HostPort === port && ["127.0.0.1", "::1"].includes(p.HostIp),
    )
  )
    throw new Error("frontend_port_mismatch");
}
export function checkProfile(
  result: MonitoringSessionResult,
  backend: { id: string; source_sha256: string },
  previous: unknown,
) {
  const {
    runtime_provenance: runtime,
    created_at: _created,
    ...profile
  } = result.model_profile!;
  if (
    !runtime?.container_id ||
    runtime.container_id.length < 12 ||
    !backend.id.startsWith(runtime.container_id) ||
    runtime.source_sha256 !== backend.source_sha256 ||
    (previous && !isDeepStrictEqual(profile, previous))
  )
    throw new Error("backend_or_profile_mismatch");
  return profile;
}
export interface AttemptRow {
  scenario_id: string;
  viewport: string;
  phase: string;
  status: string;
  browser_seconds: number | null;
}
export function summaries(rows: AttemptRow[]) {
  const groups = new Map<string, AttemptRow[]>();
  for (const row of rows.filter((r) => r.phase === "measured")) {
    const key = `${row.scenario_id}/${row.viewport}`;
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return Object.fromEntries(
    [...groups].map(([key, group]) => {
      const values = group
        .filter(
          (r) =>
            r.status === "completed" &&
            typeof r.browser_seconds === "number" &&
            Number.isFinite(r.browser_seconds) &&
            r.browser_seconds >= 0,
        )
        .map((r) => r.browser_seconds!)
        .sort((a, b) => a - b);
      const n = values.length;
      return [
        key,
        {
          attempted: group.length,
          completed: n,
          failed: group.length - n,
          seconds: {
            n,
            min: n ? values[0] : null,
            max: n ? values[n - 1] : null,
            median: n
              ? (values[Math.floor((n - 1) / 2)] + values[Math.floor(n / 2)]) /
                2
              : null,
            p95: n ? values[Math.ceil(0.95 * n) - 1] : null,
          },
        },
      ];
    }),
  );
}
