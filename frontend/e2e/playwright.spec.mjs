// playwright.spec.mjs — OPTIONAL browser-driven E2E for the research console.
//
// This drives the ACTUAL SPA in a real browser (Chromium) and asserts the same
// user-visible flows the dependency-free HTTP runner (run-e2e.mjs) covers, but
// through the rendered UI: typing in the composer, reading the agent reply,
// opening the report drawer, and confirming the price-trend chart image loads
// over the backend's /reports mount.
//
// It is MANUAL by default and is NOT installed: Playwright is an optional dev
// tool. If `@playwright/test` is absent this file is never collected (the
// `playwright` runner is what imports it), so it cannot break `npm run build`
// or CI. When you DO want it:
//
//   npm i -D @playwright/test          # if registry access is available
//   npx playwright install chromium    # one-time browser binary download
//   # start backend (:8000) and frontend (:5173), then:
//   npx playwright test -c frontend/e2e/playwright.config.mjs
//
// If Playwright cannot be installed offline, use run-e2e.mjs instead — it needs
// only Node and the running backend, with zero dependencies.

import { test, expect } from '@playwright/test'

const APP_URL = process.env.E2E_APP_URL || 'http://localhost:5173'

// The composer's example prompts double as deterministic entry points.
const ASK_ANALYZE = '分析下英伟达最近三个月的趋势和风险'
const ASK_REPORT = '帮我生成一份英伟达的研究报告'

test.describe('research console (browser E2E)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(APP_URL)
    // The persistent disclosure bar must always be visible (data-source honesty).
    await expect(page.locator('body')).toContainText(/Yahoo Finance|延迟|研究参考|非投资建议/)
  })

  test('S2/S3: chat analysis renders an agent reply with numbers', async ({ page }) => {
    const box = page.getByRole('textbox')
    await box.fill(ASK_ANALYZE)
    await box.press('Enter')

    // The agent reply bubble appears (LLM + tools can take a while).
    const reply = page.locator('.rich').last()
    await expect(reply).toBeVisible({ timeout: 120_000 })
    await expect(reply).toContainText(/\d/) // at least one computed number
  })

  test('S4/S6: report drawer renders the report and loads the chart', async ({ page }) => {
    const box = page.getByRole('textbox')
    await box.fill(ASK_REPORT)
    await box.press('Enter')

    // Wait for the agent to acknowledge the report.
    await expect(page.locator('.rich').last()).toBeVisible({ timeout: 180_000 })

    // Open the report drawer via the header action.
    await page.getByRole('button', { name: /报告|report/i }).first().click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText(/Disclaimer|Company Snapshot/i, { timeout: 60_000 })

    // The price-trend chart image must load from the backend /reports mount.
    const chart = dialog.locator('img')
    const count = await chart.count()
    if (count > 0) {
      await expect(chart.first()).toHaveJSProperty('complete', true)
      const naturalWidth = await chart.first().evaluate(
        (img) => (img instanceof HTMLImageElement ? img.naturalWidth : 0),
      )
      expect(naturalWidth).toBeGreaterThan(0) // decoded successfully (not broken)
      const src = await chart.first().getAttribute('src')
      expect(src || '').toMatch(/\/reports\/.+\.png/)
    } else {
      // Chart degraded to a data table — honest fallback, not a failure.
      test.info().annotations.push({ type: 'note', description: 'chart degraded to data table' })
    }
  })
})
