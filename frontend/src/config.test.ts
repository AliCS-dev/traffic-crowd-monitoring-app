import { describe, expect, it } from "vitest";

import { FrontendConfigurationError, resolveApiBaseUrl } from "./config.ts";

describe("resolveApiBaseUrl", () => {
  it("uses the local API when no value is configured", () => {
    expect(resolveApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("normalizes a configured base path", () => {
    expect(resolveApiBaseUrl("https://monitor.example/api/")).toBe(
      "https://monitor.example/api",
    );
  });

  it.each([
    "not-a-url",
    "ftp://monitor.example",
    "https://user:secret@monitor.example",
    "https://monitor.example?mode=test",
    "https://monitor.example#status",
  ])("rejects unsafe or ambiguous value %s", (value) => {
    expect(() => resolveApiBaseUrl(value)).toThrow(FrontendConfigurationError);
  });
});
