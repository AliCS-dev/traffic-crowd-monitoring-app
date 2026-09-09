import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5174",
    browserName: "chromium",
    locale: "en-GB",
    timezoneId: "UTC",
    reducedMotion: "reduce",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "mobile", use: { viewport: { width: 320, height: 900 } } },
  ],
  webServer: {
    env: { VITE_API_BASE_URL: "http://localhost:8000" },
    command: "npm run dev -- --host localhost --port 5174 --strictPort",
    url: "http://localhost:5174",
    reuseExistingServer: false,
  },
});
