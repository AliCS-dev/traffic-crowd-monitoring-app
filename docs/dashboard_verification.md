# Dashboard Verification

We checked the dashboard for issue #76 on 9 September 2026. This record covers
application behaviour, not detection accuracy. The model evaluation results
remain in the [evaluation index](evaluation/results_index.md).

## Automated Checks

The local Python suite passed all 358 tests, including nine PostgreSQL integration
tests. The frontend passed 101 unit and component tests after incorporating the
dependency updates from `main`. Python linting and formatting, frontend linting,
formatting, type checking, and the production build were also checked.

The committed Playwright suite runs four scenarios at desktop (1440 px) and
mobile (320 px) widths. Its eight checks cover:

- Session-history failure, retry, and empty results.
- Image proportions and grid alignment within one CSS pixel.
- Keyboard cell inspection, focus transfer, and table-filter independence.
- Timestamp-ordered video navigation and missing result images.
- Backend-unavailable status and access to the application information dialog.

Six screenshot baselines cover the image grid, experimental alerts, and unavailable
service header at both widths. We inspect baseline changes before accepting them.
The fixed toolbar is hidden only in the alert-section screenshot so it does not
obscure a section taller than the viewport; the toolbar has its own screenshot.

These browser tests use controlled API responses and the tracked sample image.
Their annotations and counts are test fixtures, not model predictions or labelled
evaluation data. They do not need a running backend, Docker, or model checkpoint.
GitHub Actions runs them alongside the existing frontend quality checks.

## Live Workflow Check

With PostgreSQL 16 and the local API running, we submitted an image and a video
through the browser. Both completed and could be reopened from session history.
The API readiness check reported both the database and detector ready.

| Development session | Input | Stored result |
| --- | --- | --- |
| 73, `Issue 76 final browser smoke image` | `sample_image.jpg` | One frame, 92 detections, six grid cells, one experimental threshold event |
| 74, `Issue 76 final browser smoke video` | `test_video.mp4`, four-second sampling | Three frames at 0, 4, and 8 seconds, with 8, 12, and 11 detections; six grid cells per frame |

For every sampled frame, the sum of stored class counts matched the detection
record count, and the sum across grid cells matched the whole-frame total.
Saved images loaded, video navigation selected the expected frame records, and
the result views fitted widths of 1440, 1024, 390, and 320 pixels. Grid overlays
followed the displayed image dimensions. No browser page errors were recorded.

The session IDs belong to this development database and are not portable test
fixtures. The smoke video is a local input, not a prerequisite for CI. These
small checks establish workflow consistency, not counting accuracy or throughput.

## Fixes From Review

We corrected the narrow header so the application-information control stays
visible when the backend is unavailable. We also corrected health reporting:
a failed refresh now shows the backend as unavailable even when React Query
still retains an older successful response. A regression test covers failure
and subsequent recovery.

## Remaining Limits

The traffic detector remains experimental and failed its recorded quality gate.
Dense-crowd counting remains unsupported. Alerts describe configured threshold
events, not verified emergencies, congestion, or physical crowd density.

Class filters affect tables, not boxes already drawn into saved JPEGs. Video
counts belong to individual sampled frames, not unique tracked objects. Mixed
input sources are not combined into a timeline, and alert records are read-only.

Browser automation currently covers Chromium only. Keyboard and responsive checks
are useful regression protection, but are not a full accessibility certification
or a substitute for testing on other browsers and real mobile devices.

## Repeating Browser Checks

From `frontend/`, with Node.js 24 available:

```bash
npm ci
npx playwright install --with-deps chromium
npm run test:browser
```

The suite starts and stops a separate Vite server on port 5174. Screenshot
baselines are Linux-specific; we use Linux or WSL to compare with the committed
images. For an intentional design change, we regenerate with
`npm run test:browser -- --update-snapshots`, inspect the changed images in
`frontend/e2e/dashboard.spec.ts-snapshots/`, and then repeat the ordinary test
command. We do not regenerate baselines merely to silence a failed check.

Failure screenshots and traces are written to the ignored `frontend/test-results/`
directory. A trace can be opened with `npx playwright show-trace <trace.zip>`.
Failed CI runs retain these files as the `dashboard-browser-failures` artifact
for seven days.
