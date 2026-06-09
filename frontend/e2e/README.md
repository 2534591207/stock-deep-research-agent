# E2E scenarios (S1–S9)

End-to-end checks that drive the **real running backend** exactly as the browser
SPA does. There are two runners; you only need the first.

The frontend is a thin transport over the backend's HTTP surface — every number,
ranking, and conclusion comes from the backend, and the UI only renders Markdown.
So the primary E2E exercises that HTTP surface directly, with **zero dependencies**.

| File | What it is | Needs |
|---|---|---|
| `run-e2e.mjs` | Dependency-free Node `fetch` runner (primary) | Node ≥ 18 + a running backend |
| `playwright.spec.mjs` + `playwright.config.mjs` | Optional browser-driven E2E | `@playwright/test` + Chromium + running backend **and** frontend |

Both are **manual by default**: nothing here runs during `npm run build`, `npm run dev`,
or CI. The `e2e/` directory is outside the app's TypeScript `include` and is not
bundled, so it never affects the production build.

## Scenarios

| ID | Scenario | Key assertions |
|---|---|---|
| S1 | Health / reachability | `GET /health` → `200 {ok:true}` |
| S2 | Single-stock analysis | reply has computed numbers; discloses Yahoo Finance / delayed; **no** auto-report (report endpoint 404) |
| S3 | Comparison & relative ranking | reply returned; still **no** auto-report |
| S4 | On-demand report generation | `GET /report/{sid}/latest` → `200` markdown |
| S5 | Report content & honesty | all 9 sections; verbatim disclaimer; Yahoo Finance named; events framed non-causally; attribution never "High" |
| S6 | Chart over HTTP | report links the chart as `/reports/<file>.png` (not a filesystem path); the PNG is served by the backend |
| S7 | Follow-up citation | a question about a report item returns a reply (verbatim business-risk lookup) |
| S8 | Session isolation | a fresh `session_id` has no report (per-session memory) |
| S9 | Out-of-scope input | an A-share name is handled honestly; no fabricated US-listing data |

Skipped checks (e.g. the chart degraded to a data table, or a bonus section
unavailable) are reported as `SKIP` and do **not** fail the run — honest
degradation is expected behaviour, never an error.

## Prerequisites

Start the backend with real keys (at minimum `OPENAI_API_KEY`; bonus sources
Tavily/SEC are optional and degrade honestly when absent):

```bash
cd ../../backend
../.venv/bin/python -m uvicorn app:app --port 8000
# (or: uvicorn app:app --reload --port 8000)
```

S2–S9 drive the live LLM + tools via `POST /chat`, so the backend must be able to
reach OpenAI. The HTTP runner does **not** require the frontend dev server.

## Run — primary (no dependencies)

```bash
# from the repo root or anywhere; just needs node + the backend up
node frontend/e2e/run-e2e.mjs

# point at a different backend / 127.0.0.1
API_BASE=http://127.0.0.1:8000 node frontend/e2e/run-e2e.mjs

# longer per-request timeout (LLM turns can be slow)
E2E_TIMEOUT_MS=180000 node frontend/e2e/run-e2e.mjs
```

Exit code is `0` when all scenarios pass, `1` otherwise — suitable for scripting.

## Run — optional (browser, Playwright)

Use this only if you want to verify the rendered UI in a real browser and have
registry/binary access:

```bash
cd frontend
npm i -D @playwright/test         # if the registry is reachable
npx playwright install chromium   # one-time browser binary download

# start backend (:8000) and, in another shell, the frontend:
npm run dev                       # http://localhost:5173

# then run the spec:
npx playwright test -c e2e/playwright.config.mjs
```

If Playwright cannot be installed offline, ignore it and use `run-e2e.mjs` — it
covers the same flows over HTTP with only Node.

## Configuration

| Env var | Used by | Default |
|---|---|---|
| `API_BASE` / `VITE_API_BASE` | `run-e2e.mjs` | `http://localhost:8000` |
| `E2E_TIMEOUT_MS` | `run-e2e.mjs` | `120000` |
| `E2E_APP_URL` | Playwright | `http://localhost:5173` |
