import { test } from "node:test";
import assert from "node:assert/strict";
import {
  localOrigin,
  repetitions,
  checkStack,
  checkProfile,
  summaries,
  type ContainerIdentity,
} from "./evidence.ts";
import { analysisResultFixture } from "../src/test/analysisResultFixture.ts";

test("origin and repetition settings are bounded", () => {
  assert.equal(localOrigin("http://127.0.0.1:8086"), "http://127.0.0.1:8086");
  for (const url of [
    "https://example.com",
    "http://localhost/api",
    "http://user:pass@localhost",
    "http://localhost?x=1",
  ])
    assert.throws(() => localOrigin(url));
  for (const n of ["0", "31", "NaN", "1.5", "-1"])
    assert.throws(() => repetitions(n));
  assert.equal(repetitions("10"), 10);
});
test("stack must be disposable, running, same-project and bound to the measured port", () => {
  const backend: ContainerIdentity = {
    id: "a",
    image: "i",
    started_at: "s",
    running: true,
    service: "backend",
    project: "test",
    measurement: "disposable",
    ports: null,
  };
  const frontend: ContainerIdentity = {
    ...backend,
    id: "b",
    service: "frontend",
    ports: [{ HostIp: "127.0.0.1", HostPort: "8086" }],
  };
  checkStack(backend, frontend, "http://localhost:8086");
  assert.throws(() =>
    checkStack(
      { ...backend, measurement: null },
      frontend,
      "http://localhost:8086",
    ),
  );
  assert.throws(() =>
    checkStack(
      backend,
      { ...frontend, project: "other" },
      "http://localhost:8086",
    ),
  );
  assert.throws(() => checkStack(backend, frontend, "http://localhost:8087"));
  assert.throws(() =>
    checkStack(
      { ...backend, running: false },
      frontend,
      "http://localhost:8086",
    ),
  );
});
test("saved provenance must identify the selected backend and unchanged model", () => {
  const result = analysisResultFixture();
  const backend = { id: "a".repeat(64), source_sha256: "source" };
  assert.throws(() => checkProfile(result, backend, null));
  result.model_profile!.runtime_provenance = {
    schema_version: 1,
    captured_at: "now",
    application_commit: "commit",
    source_dirty: false,
    source_sha256: "source",
    python_version: "3",
    platform: "linux",
    dependencies: {},
    device: "cpu",
    gpu_name: null,
    cuda_version: null,
    cudnn_version: null,
    container_id: "a".repeat(12),
  };
  const profile = checkProfile(result, backend, null);
  checkProfile(result, backend, profile);
  assert.throws(() =>
    checkProfile(result, { ...backend, id: "b".repeat(64) }, profile),
  );
  result.model_profile!.confidence = 0.9;
  assert.throws(() => checkProfile(result, backend, profile));
});
test("summaries exclude warmups, retain failures and separate viewports", () => {
  const row = {
    scenario_id: "I1",
    viewport: "desktop",
    phase: "measured",
    status: "completed",
    browser_seconds: 1,
  };
  const summary = summaries([
    row,
    { ...row, browser_seconds: 3 },
    { ...row, status: "failed", browser_seconds: 99 },
    { ...row, phase: "warmup", browser_seconds: 100 },
    { ...row, viewport: "mobile", browser_seconds: 5 },
  ]);
  assert.deepEqual(summary["I1/desktop"], {
    attempted: 3,
    completed: 2,
    failed: 1,
    seconds: { n: 2, min: 1, max: 3, median: 2, p95: 3 },
  });
  assert.equal(summary["I1/mobile"].seconds.median, 5);
});
