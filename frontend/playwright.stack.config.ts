import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./stack-tests",
  outputDir: "./test-results/stack",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.STACK_BASE_URL ?? "http://localhost:8080",
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 15_000,
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { viewport: { width: 320, height: 900 } } },
  ],
});
