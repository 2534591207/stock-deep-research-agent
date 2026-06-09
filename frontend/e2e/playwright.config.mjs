// playwright.config.mjs — OPTIONAL config for the browser-driven E2E spec.
//
// Only used when you explicitly run `npx playwright test -c
// frontend/e2e/playwright.config.mjs`. It is not referenced by `npm run build`,
// `npm run dev`, or CI. Requires `@playwright/test` + a Chromium binary
// (`npx playwright install chromium`). If those are unavailable offline, use the
// dependency-free node runner instead: `node frontend/e2e/run-e2e.mjs`.
//
// Servers are assumed to be already running (backend :8000, frontend :5173).
// To have Playwright start the Vite dev server automatically, uncomment the
// `webServer` block below.

import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  testMatch: /playwright\.spec\.mjs$/,
  fullyParallel: false,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_APP_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  // webServer: {
  //   command: 'npm run dev',
  //   url: 'http://localhost:5173',
  //   reuseExistingServer: true,
  //   timeout: 120_000,
  // },
})
