#!/usr/bin/env node
/**
 * run-e2e.mjs — dependency-free end-to-end scenarios (S1–S9) against the REAL
 * running backend, exercised exactly as the browser SPA does over HTTP.
 *
 * Why a plain Node script (no Playwright)?
 *   The app's UI is a thin transport over three backend endpoints (POST /chat,
 *   GET /report/{sid}/latest, GET /health) plus the static chart mount
 *   (GET /reports/<file>). Every number, ranking, and conclusion is produced by
 *   the backend; the frontend renders Markdown and never computes anything. So a
 *   faithful E2E only needs to drive those endpoints with a stable session id and
 *   assert the contract + honesty red lines on the live responses. This script
 *   uses Node's built-in global `fetch` (Node >= 18) with ZERO dependencies, so
 *   it runs offline tomorrow with just `node` — no browser binaries to download.
 *   A browser-driven Playwright spec lives alongside (playwright.spec.mjs) and is
 *   self-skipping when Playwright is not installed.
 *
 * Prerequisites (NOT started by this script):
 *   - Backend running and reachable (default http://localhost:8000). It must be
 *     started with real keys (OPENAI_API_KEY at minimum) because /chat drives the
 *     live LLM + tools. Bonus sources (Tavily/SEC) may be absent — affected report
 *     sections degrade to honest notes and must NOT block the core analysis.
 *   - The frontend itself does not need to be running for the HTTP E2E; it is a
 *     pure transport client. (The Playwright spec, when used, does need the dev
 *     server.)
 *
 * Usage:
 *   node frontend/e2e/run-e2e.mjs
 *   API_BASE=http://127.0.0.1:8000 node frontend/e2e/run-e2e.mjs
 *   E2E_TIMEOUT_MS=120000 node frontend/e2e/run-e2e.mjs   # per-request timeout
 *
 * Exit code: 0 if all scenarios pass, 1 otherwise. Skipped (degraded-but-honest)
 * checks do not fail the run. This script is MANUAL by default — it is not part
 * of `npm run build` and runs nothing during CI unless invoked explicitly.
 */

// --------------------------------------------------------------------------
// Config
// --------------------------------------------------------------------------

const API_BASE = (
  process.env.API_BASE ||
  process.env.VITE_API_BASE ||
  'http://localhost:8000'
).replace(/\/+$/, '')

const REQ_TIMEOUT_MS = Number(process.env.E2E_TIMEOUT_MS || 120_000)

// One stable session id for the whole run — this is exactly how the SPA keeps
// multi-turn memory (thread_id = session_id on the backend). A second id is used
// to prove session isolation (S8).
const SID = `e2e-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
const SID_OTHER = `e2e-other-${Math.random().toString(36).slice(2, 8)}`

// --------------------------------------------------------------------------
// Tiny test harness (no deps)
// --------------------------------------------------------------------------

let passed = 0
let failed = 0
let skipped = 0
const failures = []

const C = {
  reset: '\x1b[0m', red: '\x1b[31m', green: '\x1b[32m',
  yellow: '\x1b[33m', cyan: '\x1b[36m', dim: '\x1b[2m',
}

function ok(name, detail = '') {
  passed++
  console.log(`  ${C.green}PASS${C.reset} ${name}${detail ? ` ${C.dim}— ${detail}${C.reset}` : ''}`)
}
function bad(name, detail = '') {
  failed++
  failures.push(`${name}${detail ? ` — ${detail}` : ''}`)
  console.log(`  ${C.red}FAIL${C.reset} ${name}${detail ? ` ${C.dim}— ${detail}${C.reset}` : ''}`)
}
function skip(name, detail = '') {
  skipped++
  console.log(`  ${C.yellow}SKIP${C.reset} ${name}${detail ? ` ${C.dim}— ${detail}${C.reset}` : ''}`)
}
function assert(cond, name, detail = '') {
  if (cond) ok(name, detail)
  else bad(name, detail)
  return !!cond
}
function section(title) {
  console.log(`\n${C.cyan}${title}${C.reset}`)
}

// --------------------------------------------------------------------------
// HTTP helpers — same shapes the SPA uses (see frontend/src/lib/api.ts)
// --------------------------------------------------------------------------

async function withTimeout(promiseFactory) {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), REQ_TIMEOUT_MS)
  try {
    return await promiseFactory(ctrl.signal)
  } finally {
    clearTimeout(t)
  }
}

async function getHealth() {
  return withTimeout(async (signal) => {
    const res = await fetch(`${API_BASE}/health`, { signal })
    let body = null
    try { body = await res.json() } catch { /* ignore */ }
    return { status: res.status, body }
  })
}

async function postChat(sessionId, message) {
  return withTimeout(async (signal) => {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
      signal,
    })
    let body = null
    try { body = await res.json() } catch { /* ignore */ }
    const reply = body && typeof body.reply === 'string' ? body.reply : ''
    return { status: res.status, reply, body }
  })
}

async function getLatestReport(sessionId) {
  return withTimeout(async (signal) => {
    const res = await fetch(
      `${API_BASE}/report/${encodeURIComponent(sessionId)}/latest`,
      { headers: { Accept: 'text/markdown, text/plain' }, signal },
    )
    const text = res.status === 200 ? await res.text() : ''
    return { status: res.status, markdown: text }
  })
}

async function headOrGet(url) {
  return withTimeout(async (signal) => {
    // The static mount supports GET; we read only the first bytes we need.
    const res = await fetch(url, { signal })
    const buf = res.status === 200 ? new Uint8Array(await res.arrayBuffer()) : new Uint8Array()
    return { status: res.status, contentType: res.headers.get('content-type') || '', bytes: buf }
  })
}

// --------------------------------------------------------------------------
// Honesty / contract assertions reused across scenarios
// --------------------------------------------------------------------------

const CAUSAL_VERBS = /(caused|drove|triggered|because of|due to|resulted in|led to)/i
const SOURCE_RE = /(yahoo\s*finance|雅虎|延迟|delayed|数据来源|data source)/i

function assertNoHighConfidenceCausation(text, label) {
  // The report/replies frame news as "may be related"; they must never assert a
  // cause for a price move, and attribution confidence must never read "High".
  const hasHighAttribution = /attribution[^\n]*\bHigh\b/i.test(text)
  assert(!hasHighAttribution, `${label}: attribution confidence is never 'High'`)
  // We do not hard-fail on the presence of a causal verb anywhere (it may appear
  // inside a verbatim filing risk title or a headline), but we DO require the
  // explicit non-causal disclaimer to be present whenever events are surfaced.
}

// --------------------------------------------------------------------------
// Scenarios S1–S9
// --------------------------------------------------------------------------

async function main() {
  console.log(`${C.cyan}E2E (S1–S9) → ${API_BASE}${C.reset}`)
  console.log(`${C.dim}session=${SID}  timeout=${REQ_TIMEOUT_MS}ms${C.reset}`)

  // --- S1: health / reachability ----------------------------------------
  section('S1 — Health & reachability')
  let health
  try {
    health = await getHealth()
  } catch (e) {
    bad('S1 backend reachable', String(e?.message || e))
    return finish() // nothing else can run if the backend is down
  }
  if (!assert(health.status === 200 && health.body && health.body.ok === true,
    'S1 GET /health → 200 {ok:true}', `status=${health.status}`)) {
    return finish()
  }

  // --- S2: single-stock analysis (numbers from code, source disclosed) ---
  section('S2 — Single-stock analysis')
  const s2 = await postChat(SID, '分析一下英伟达（NVDA）最近一个月的走势和风险')
  assert(s2.status === 200 && s2.reply.length > 0, 'S2 POST /chat returns a reply', `status=${s2.status}`)
  assert(SOURCE_RE.test(s2.reply), 'S2 reply discloses data source / delayed nature')
  assert(/\d/.test(s2.reply), 'S2 reply contains computed numbers')
  // A single-stock analysis must NOT auto-emit a report.
  const s2Report = await getLatestReport(SID)
  assert(s2Report.status === 404, 'S2 analysis does NOT auto-create a report (404)', `status=${s2Report.status}`)

  // --- S3: comparison + relative ranking --------------------------------
  section('S3 — Comparison & relative ranking')
  const s3 = await postChat(SID, '英伟达和苹果比，最近一个月谁的波动更大？')
  assert(s3.status === 200 && s3.reply.length > 0, 'S3 comparison returns a reply', `status=${s3.status}`)
  // Still no report from a comparison.
  const s3Report = await getLatestReport(SID)
  assert(s3Report.status === 404, 'S3 comparison does NOT auto-create a report (404)', `status=${s3Report.status}`)

  // --- S4: on-demand report generation ----------------------------------
  section('S4 — On-demand report generation')
  const s4 = await postChat(SID, '帮我生成一份英伟达（NVDA）最近一个月的研究报告')
  assert(s4.status === 200 && s4.reply.length > 0, 'S4 report request returns a reply', `status=${s4.status}`)
  const report = await getLatestReport(SID)
  const haveReport = assert(report.status === 200 && report.markdown.length > 0,
    'S4 GET /report/{sid}/latest → 200 markdown', `status=${report.status}`)

  let chartUrl = null
  if (haveReport) {
    const md = report.markdown

    // --- S5: report content & honesty red lines -------------------------
    section('S5 — Report content & honesty')
    const NINE_SECTIONS = [
      'Company Snapshot', 'Price Trend', 'Observed Market Risk', 'Significant Move',
      'Related Events', 'Financial & Filing Highlights', 'Business Risks',
      'Short-term Market View', 'Evidence & Limitations',
    ]
    const missing = NINE_SECTIONS.filter((s) => !md.includes(s))
    assert(missing.length === 0, 'S5 report has all 9 sections', missing.length ? `missing: ${missing.join(', ')}` : '')
    assert(/Disclaimer/i.test(md) && /does not constitute investment advice/i.test(md),
      'S5 report carries the verbatim disclaimer')
    assert(/Yahoo Finance/i.test(md), 'S5 report names Yahoo Finance as the (delayed) source')
    assert(/does not prove causation|not attributed to any cause|MAY be related/i.test(md),
      'S5 report frames events non-causally')
    assertNoHighConfidenceCausation(md, 'S5')

    // --- S6: chart served over HTTP (the integration fix) ---------------
    section('S6 — Chart over HTTP (/reports static mount)')
    const m = md.match(/!\[[^\]]*\]\((\/reports\/[^)]+\.png)\)/)
    if (m) {
      chartUrl = m[1]
      assert(!chartUrl.startsWith('/Users') && !chartUrl.includes('_reports/'),
        'S6 chart link is an HTTP /reports URL (no filesystem path)', chartUrl)
      const img = await headOrGet(`${API_BASE}${chartUrl}`)
      assert(img.status === 200 && img.contentType.startsWith('image/'),
        'S6 chart PNG is served by the backend', `status=${img.status} type=${img.contentType}`)
      const isPng = img.bytes.length >= 8 &&
        img.bytes[0] === 0x89 && img.bytes[1] === 0x50 && img.bytes[2] === 0x4e && img.bytes[3] === 0x47
      assert(isPng, 'S6 served chart is a valid PNG')
    } else {
      // The chart degrades to a data table on render failure — honest, not a bug.
      skip('S6 chart link present', 'report degraded to the normalized data table (no chart)')
    }
  } else {
    skip('S5 report content checks', 'no report available')
    skip('S6 chart checks', 'no report available')
  }

  // --- S7: follow-up citation from the existing report ------------------
  section('S7 — Follow-up citation from the report')
  const s7 = await postChat(SID, '报告里英伟达的第一条业务风险是什么？请逐字给出。')
  assert(s7.status === 200 && s7.reply.length > 0, 'S7 follow-up returns a reply', `status=${s7.status}`)

  // --- S8: session isolation --------------------------------------------
  section('S8 — Session isolation')
  const otherReport = await getLatestReport(SID_OTHER)
  assert(otherReport.status === 404,
    'S8 a fresh session has no report (memory is per-session)', `status=${otherReport.status}`)

  // --- S9: honest degradation for unrecognized / out-of-scope ----------
  section('S9 — Honest handling of out-of-scope input')
  const s9 = await postChat(SID, '帮我分析一下贵州茅台（600519，A股）')
  assert(s9.status === 200 && s9.reply.length > 0, 'S9 out-of-scope returns a reply', `status=${s9.status}`)
  // The assistant must not fabricate US metrics for a non-US-listed name; it
  // should decline / clarify. We assert it did NOT invent a fake US ticker line.
  assert(!/NYSE|NASDAQ/i.test(s9.reply) || /A股|美股|US-listed|不支持|无法|仅覆盖/i.test(s9.reply),
    'S9 does not fabricate US-listing data for an A-share name')

  return finish()
}

function finish() {
  console.log(
    `\n${C.cyan}Summary${C.reset}: ` +
    `${C.green}${passed} passed${C.reset}, ` +
    `${failed ? C.red : C.dim}${failed} failed${C.reset}, ` +
    `${C.yellow}${skipped} skipped${C.reset}`,
  )
  if (failed > 0) {
    console.log(`\n${C.red}Failures:${C.reset}`)
    for (const f of failures) console.log(`  - ${f}`)
    process.exitCode = 1
  } else {
    console.log(`\n${C.green}All E2E scenarios passed.${C.reset}`)
    process.exitCode = 0
  }
}

main().catch((e) => {
  console.error(`\n${C.red}E2E runner crashed:${C.reset}`, e)
  process.exitCode = 1
})
