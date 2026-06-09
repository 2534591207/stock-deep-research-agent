"""app.py — FastAPI application for the two-layer US stock research agent.

Endpoints:
  GET  /health                            → {ok: true}   (no key/agent dependency)
  POST /chat                              → {reply, reports|null}  (build_agent singleton)
  GET  /report/{sid}                      → JSON list of per-stock reports (newest-first)
  GET  /report/{sid}/latest               → text/markdown (most-recent report)
  GET  /report/{sid}/{report_id}          → text/markdown (one per-stock report)
  GET  /reports/{file}                    → static PNG chart files (for report viewing)

Startup:
  require_keys() is called at startup via lifespan; missing keys abort startup.
  /health is excluded from the key requirement (registered before lifespan check
  would block it — health always responds 200 regardless of key state).

Cross-cutting (frontend integration):
  - CORS is enabled so the browser SPA on a different origin can call /chat,
    /report/*, and /health.
  - The generated price-trend charts under _reports/ are served as static files
    at /reports so the report viewer can load them over HTTP.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel

from config import (
    ALLOWED_UPLOAD_EXTENSIONS,
    MAX_UPLOAD_MB,
    require_keys,
)
from services import doc_store
from services.document import DocumentError, build_uploaded_doc, ensure_index
from services.progress import report_progress


# ---------------------------------------------------------------------------
# In-memory report store: session_id → ORDERED LIST of StoredReport.
#
# A report is now PER-STOCK and self-contained. Each generation appends ONE
# entry per stock to the session's list (append-only, oldest-first). The GET
# list endpoint returns them newest-first.
# ---------------------------------------------------------------------------


class StoredReport(BaseModel):
    report_id: str
    title: str
    symbol: str
    markdown: str


_report_store: dict[str, list[StoredReport]] = {}


# ---------------------------------------------------------------------------
# Lifespan: startup key validation (fail-fast, no mock/demo fallback)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    require_keys()          # raises RuntimeError if any core key is missing
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="US Stock Research Agent", lifespan=lifespan)


# ---------------------------------------------------------------------------
# CORS — allow the browser SPA (separate dev origin) to call the API.
# The Vite dev server runs on :5173; both localhost and 127.0.0.1 are listed
# explicitly (browsers treat them as distinct origins). A regex additionally
# permits other localhost ports used in dev (e.g. the Vite preview server on
# :4173). All methods and headers are allowed. Tighten for production deploys.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Static report assets — serve generated price-trend charts so the report
# viewer can load them over HTTP (the report markdown references them by name).
# Mounted defensively: the directory is created if absent so startup never
# fails when no report has been generated yet.
# ---------------------------------------------------------------------------

_REPORTS_DIR = Path(__file__).resolve().parent / "_reports"
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(_REPORTS_DIR)), name="reports")


# ---------------------------------------------------------------------------
# Helper: inline /reports/<FILE>.png images as base64 data URIs
# ---------------------------------------------------------------------------

# Matches Markdown image targets that are server-relative /reports/*.png paths,
# e.g. ![Price Trend Chart](/reports/abc123_NVDA.png)
_REPORTS_IMG_RE = re.compile(r"(!\[[^\]]*\]\()(/reports/[^)\s]+\.png)(\))")


def inline_report_images(markdown: str) -> str:
    """Replace every /reports/<FILE>.png image target with a base64 data URI.

    This makes the Markdown self-contained: the chart PNG is embedded directly
    so the file is usable offline (no server needed).

    Rules:
    - Only rewrites paths that start with ``/reports/`` and end with ``.png``.
    - Reads the PNG from ``_REPORTS_DIR`` (the same directory the static mount
      serves). If the file does not exist on disk, the reference is left
      unchanged — never crashes.
    - Leaves ``http(s):`` and ``data:`` targets untouched (they are already
      absolute or already inlined).
    """

    def _replace(m: re.Match) -> str:
        prefix, path, suffix = m.group(1), m.group(2), m.group(3)
        # Strip the leading "/reports/" to get the bare filename
        filename = path[len("/reports/"):]
        png_path = _REPORTS_DIR / filename
        try:
            data = png_path.read_bytes()
        except OSError:
            # File missing — leave the original reference intact
            return m.group(0)
        b64 = base64.b64encode(data).decode("ascii")
        return f"{prefix}data:image/png;base64,{b64}{suffix}"

    return _REPORTS_IMG_RE.sub(_replace, markdown)


# ---------------------------------------------------------------------------
# /health — completely decoupled from agent/keys
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Health check. Always returns 200 {ok: true}. Does not depend on keys or agent."""
    return {"ok": True}


# ---------------------------------------------------------------------------
# POST /upload — single financial-report file → extract → chunk → embed → store
#
# NEW, purely additive. Stores ONE document per session (replace on re-upload) in
# the document store (separate from the report store). Errors:
#   415 unsupported type · 413 too large · 422 no extractable text (scanned PDF;
#   OCR is not supported this phase).
# ---------------------------------------------------------------------------

# Injectable embedder for the upload pipeline (None → real OpenAI embeddings via
# services.document; tests inject a deterministic offline fake).
_UPLOAD_EMBEDDER: Any = None


def set_upload_embedder(embedder: Any) -> None:
    """Replace the module-level upload embedder (for testing)."""
    global _UPLOAD_EMBEDDER
    _UPLOAD_EMBEDDER = embedder


def _upload_ext(filename: str) -> str:
    name = (filename or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


@app.post("/upload")
async def upload(file: UploadFile = File(...), session_id: str = Form(...)) -> StreamingResponse:
    """Accept ONE financial-report file for a session, then STREAM its processing
    progress as NDJSON while building the embedding index AT UPLOAD time.

    Validation (extension + size) happens FIRST and returns a normal HTTP error
    (415 unsupported / 413 too large) BEFORE any streaming begins. Otherwise the
    response is ``application/x-ndjson``, one JSON object per line:

      {"type":"phase","phase":"extract","label":"读取并解析文件"}
      {"type":"phase","phase":"index","label":"建立向量索引","done":d,"total":t}  (repeated)
      {"type":"ready","filename":...,"pages":...,"chars":...,"index_truncated":bool}
      {"type":"error","message":"..."}   (e.g. scanned PDF with no extractable text)

    The final line is exactly one ``ready`` (success) or one ``error``. The doc is
    stored WITH its built embeddings, so subsequent questions are instant (the
    analyze_document tool's ensure_index becomes a near-instant no-op).
    """
    # ── 1. Validate ext/size FIRST → real HTTP status BEFORE streaming. ─────────
    ext = _upload_ext(file.filename or "")
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"不支持的文件类型：{ext or file.filename}。"
                f"仅支持 {', '.join(ALLOWED_UPLOAD_EXTENSIONS)}。"
            ),
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，超过 {MAX_UPLOAD_MB}MB 上限。",
        )

    filename = file.filename or "upload"
    embedder = _UPLOAD_EMBEDDER

    async def gen():
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def push(ev: dict) -> None:
            # Called from the worker thread → hand the event to the async queue.
            loop.call_soon_threadsafe(q.put_nowait, ev)

        # Phase: extract — emitted before the (blocking) extract+chunk runs.
        yield json.dumps(
            {"type": "phase", "phase": "extract", "label": "读取并解析文件"},
            ensure_ascii=False,
        ) + "\n"

        # extract + chunk in a worker thread (PyMuPDF + chunking are blocking).
        try:
            doc = await asyncio.to_thread(build_uploaded_doc, data, filename, embedder)
        except DocumentError as exc:
            yield json.dumps(
                {"type": "error", "message": str(exc)}, ensure_ascii=False
            ) + "\n"
            return
        except Exception as exc:  # noqa: BLE001 — surface the real error to the stream
            yield json.dumps(
                {"type": "error", "message": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            ) + "\n"
            return

        # Store the doc now so a question arriving mid-index can still find it
        # (ensure_index in analyze_document remains a safety net).
        doc_store.put_document(session_id, doc)

        # Build the embedding index AT UPLOAD time, in a worker thread, pushing a
        # phase:index event (done/total) after each embedding batch completes.
        def on_progress(done: int, total: int) -> None:
            push({"type": "phase", "phase": "index", "label": "建立向量索引",
                  "done": done, "total": total})

        async def run_index():
            return await asyncio.to_thread(
                ensure_index, doc, embedder, on_progress
            )

        task = asyncio.create_task(run_index())
        try:
            while not (task.done() and q.empty()):
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=0.1)
                    yield json.dumps(ev, ensure_ascii=False) + "\n"
                except asyncio.TimeoutError:
                    continue
            task.result()  # re-raise any worker exception
            yield json.dumps(
                {
                    "type": "ready",
                    "filename": doc.filename,
                    "pages": doc.meta.get("pages", 1),
                    "chars": doc.meta.get("chars", len(doc.text)),
                    "index_truncated": doc.index_truncated,
                },
                ensure_ascii=False,
            ) + "\n"
        except Exception as exc:  # noqa: BLE001 — surface the real error to the stream
            yield json.dumps(
                {"type": "error", "message": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    message: str


class ReportRef(BaseModel):
    """A lightweight reference to one per-stock report (snake_case JSON)."""
    report_id: str
    title: str
    symbol: str
    download_ref: str


class ReportListItem(BaseModel):
    """One entry in the GET /report/{sid} list (no markdown — metadata only)."""
    report_id: str
    title: str
    symbol: str


class ChatResponse(BaseModel):
    reply: str
    # Non-null ONLY when generate_report ran THIS turn (turn-scoped). On a pure
    # chat / analysis / comparison turn this stays None.
    reports: list[ReportRef] | None = None


# ---------------------------------------------------------------------------
# Lazy agent import (avoids importing ChatOpenAI at module level which would
# fail if openai isn't configured yet; also makes /health independent)
# ---------------------------------------------------------------------------

def _get_agent() -> Any:
    from agent import build_agent
    return build_agent()


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

def _build_turn_messages(req: ChatRequest) -> list[dict]:
    """Assemble THIS turn's messages for the agent invoke.

    Always includes the user's message. When the session has an uploaded
    document (via doc_store), a lightweight system-role awareness message is
    PREPENDED so the LLM knows a financial-report file is attached and will call
    analyze_document instead of asking the user to upload one (fixes the
    out-of-band /upload bug where the conversation had no signal a file existed).

    ADDITIVE & no-op when no document exists: in that case the returned list is
    byte-for-byte identical to the previous behaviour ([{"role":"user", ...}]),
    so every non-document flow is unchanged.
    """
    doc = doc_store.get_document(req.session_id)
    if doc is None:
        return [{"role": "user", "content": req.message}]
    return [
        {
            "role": "system",
            "content": (
                f"[System note] A financial-report file is uploaded in this session: \"{doc.filename}\". "
                "Call analyze_document ONLY when the user explicitly asks about the content of "
                "this uploaded file itself (e.g. what the filing/document says, the risks it "
                "lists, a specific section, or 'analyze this document'); answer grounded in the "
                "file's content and never ask the user to re-upload. "
                "But when the user asks about a STOCK's price / return / volatility / risk "
                "level / significant moves / biggest up-or-down day (results that come from "
                "analyze_stocks or already appear earlier in this conversation), answer from "
                "the conversation context or call analyze_stocks — do NOT switch to "
                "analyze_document merely because a document is attached. "
                "Example: right after a stock analysis, follow-ups like 'which day did it drop "
                "the most / what's the return / what's the risk level' are about that STOCK "
                "(the answer is in the analysis/conversation), not about the uploaded document. "
                "As always, reply in the user's language."
            ),
        },
        {"role": "user", "content": req.message},
    ]


def _invoke_agent_collect(
    req: ChatRequest, callbacks: list | None = None
) -> tuple[str, list[ReportRef] | None]:
    """Invoke the agent for ONE turn and collect (reply, reports).

    Shared by both POST /chat (synchronous) and POST /chat/stream (NDJSON) so
    both endpoints use IDENTICAL turn-scoping: ``reports`` is populated ONLY when
    generate_report ran this turn (scanned via _extract_this_turn_reports), and
    each ReportRef carries download_ref=f"/report/{sid}/{report_id}". The per-stock
    reports produced this turn are persisted to the in-memory store as a side
    effect (same as the original /chat behaviour). Returns (reply, reports|None).

    ``callbacks`` (optional) is a list of LangChain callback handlers attached to
    the agent invocation. /chat/stream passes a token-streaming handler so the
    model's on_llm_new_token fires; /chat passes None (unchanged behaviour).
    """
    config: dict[str, Any] = {"configurable": {"thread_id": req.session_id}}
    if callbacks:
        config["callbacks"] = callbacks
    agent = _get_agent()
    # Set the current session so the analyze_document tool can resolve this
    # session's uploaded document. ADDITIVE: existing tools never read this
    # contextvar, so their behaviour is unchanged. Reset in finally.
    _sid_token = doc_store.current_session_id.set(req.session_id)
    try:
        result = agent.invoke(
            {"messages": _build_turn_messages(req)},
            config=config,
        )
    finally:
        doc_store.current_session_id.reset(_sid_token)
    last_msg = result["messages"][-1]
    reply: str = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)

    # Detect per-stock reports produced THIS turn and persist them.
    # Scope: only messages after the last HumanMessage (this turn's input).
    this_turn_reports = _extract_this_turn_reports(result["messages"])

    reports_field: list[ReportRef] | None = None
    if this_turn_reports:
        stored = _report_store.setdefault(req.session_id, [])
        # APPEND-only: never overwrite the existing list. Guard against appending
        # a report_id that is already stored (e.g. an overlapping/re-run turn) so
        # the list stays unique while still keeping EVERY per-stock report.
        existing_ids = {r.report_id for r in stored}
        stored.extend(r for r in this_turn_reports if r.report_id not in existing_ids)
        reports_field = [
            ReportRef(
                report_id=r.report_id,
                title=r.title,
                symbol=r.symbol,
                download_ref=f"/report/{req.session_id}/{r.report_id}",
            )
            for r in this_turn_reports
        ]

    return reply, reports_field


@app.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(req: ChatRequest) -> ChatResponse:
    """Process a chat message and return the agent's reply.

    Uses thread_id = session_id for MemorySaver-based multi-turn memory.
    Extracts the last message from the agent result as the reply.
    Persists any per-stock reports produced THIS turn to the in-memory store and
    surfaces them as ChatResponse.reports (turn-scoped; None otherwise).
    """
    try:
        reply, reports_field = _invoke_agent_collect(req)
        return ChatResponse(reply=reply, reports=reports_field)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface real error for debugging
        import sys
        import traceback

        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# POST /chat/stream — NDJSON live progress
#
# Same request body as /chat. Streams one compact JSON object per line:
#   - {"type":"stage", "symbol":..., "stage":..., "status":...}  (live, per stage)
#   - {"type":"done", "reply":..., "reports":[...] | null}        (final, exactly once)
#   - {"type":"error", "message":...}                             (on failure)
#
# The deterministic report pipeline (services/report.py::build_report) runs in a
# worker thread via asyncio.to_thread; its emit_stage() calls push events through
# a contextvar sink we set BEFORE spawning the task (so the copied context carries
# it into the worker thread). The sink hands events to an asyncio.Queue in a
# thread-safe way (loop.call_soon_threadsafe). The final "done" event reuses the
# SAME (reply, reports) extraction as /chat via _invoke_agent_collect.
# ---------------------------------------------------------------------------

class _TokenStreamHandler(BaseCallbackHandler):
    """LangChain callback that forwards each LLM content token to a sink.

    on_llm_new_token fires once per generated token on the thread running the
    LLM (the worker thread spawned by asyncio.to_thread). We push a compact
    {"type":"token","text":token} event through the provided ``sink`` — the same
    loop.call_soon_threadsafe-backed sink the progress events use — so tokens and
    stage events interleave on a single asyncio.Queue in arrival order. Empty
    tokens (some providers emit a final empty token) are skipped. The final
    authoritative ``reply`` is still carried by the ``done`` event; these token
    events are purely incremental display.
    """

    def __init__(self, sink: Any) -> None:
        self._sink = sink

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:  # noqa: D401
        if not token:
            return
        self._sink({"type": "token", "text": token})


@app.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    async def gen():
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def sink(ev: dict) -> None:
            loop.call_soon_threadsafe(q.put_nowait, ev)  # worker thread -> async queue

        # Token-streaming callback: the agent's LLM (ChatOpenAI(streaming=True))
        # fires on_llm_new_token for every content token of every LLM call. Those
        # callbacks run on the worker thread (the agent runs in asyncio.to_thread),
        # so — exactly like the progress sink — we hand each token to the async
        # queue thread-safely via loop.call_soon_threadsafe. Tool-routing LLM calls
        # emit no content tokens, so in practice these are the final answer's tokens.
        token_handler = _TokenStreamHandler(sink)

        token = report_progress.set(sink)  # set BEFORE creating the task so the copied context carries it

        async def run_agent():
            return await asyncio.to_thread(
                _invoke_agent_collect, req, [token_handler]
            )  # to_thread copies the contextvar (incl. sink)

        task = asyncio.create_task(run_agent())
        try:
            while not (task.done() and q.empty()):
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=0.1)
                    yield json.dumps(ev, ensure_ascii=False) + "\n"
                except asyncio.TimeoutError:
                    continue
            reply, reports = task.result()
            reports_payload = (
                [r.model_dump() for r in reports] if reports else None
            )
            yield json.dumps(
                {"type": "done", "reply": reply, "reports": reports_payload},
                ensure_ascii=False,
            ) + "\n"
        except Exception as exc:  # noqa: BLE001 — surface the real error to the stream
            yield json.dumps(
                {"type": "error", "message": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            ) + "\n"
        finally:
            report_progress.reset(token)

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# GET /report/{session_id}  → JSON list (newest-first)
# ---------------------------------------------------------------------------

@app.get("/report/{session_id}")
def list_reports(session_id: str) -> dict:
    """List this session's per-stock reports (metadata only), newest-first.

    Returns {"reports": [{"report_id","title","symbol"}, ...]}. An unknown
    session yields an empty list (not a 404) so the frontend panel can render
    "no reports yet" without special-casing.
    """
    stored = _report_store.get(session_id, [])
    items = [
        ReportListItem(report_id=r.report_id, title=r.title, symbol=r.symbol)
        for r in reversed(stored)
    ]
    return {"reports": [i.model_dump() for i in items]}


# ---------------------------------------------------------------------------
# GET /report/{session_id}/latest  → text/markdown of the most-recent report
# (back-compat; kept working). Registered BEFORE the {report_id} route so
# "latest" is never captured as a report_id.
# ---------------------------------------------------------------------------

@app.get("/report/{session_id}/latest")
def get_latest_report(session_id: str) -> PlainTextResponse:
    """Return the most recent report markdown for this session as text/markdown.

    Raises 404 if no report has been generated in this session yet.
    """
    stored = _report_store.get(session_id)
    if not stored:
        raise HTTPException(status_code=404, detail="No report found for this session.")
    markdown = stored[-1].markdown
    return PlainTextResponse(content=inline_report_images(markdown), media_type="text/markdown")


# ---------------------------------------------------------------------------
# GET /report/{session_id}/{report_id}  → text/markdown (single, downloadable)
# ---------------------------------------------------------------------------

@app.get("/report/{session_id}/{report_id}")
def get_report(session_id: str, report_id: str) -> PlainTextResponse:
    """Return ONE per-stock report markdown as a clean text/markdown download.

    When the image host is configured the chart is already a GitHub raw URL in
    the markdown (so the download is self-contained). Otherwise the local
    /reports/<file>.png reference is inlined as a base64 data URI so the file
    still renders the chart offline. Raises 404 when the report is unknown.
    """
    stored = _report_store.get(session_id, [])
    for r in stored:
        if r.report_id == report_id:
            return PlainTextResponse(
                content=inline_report_images(r.markdown),
                media_type="text/markdown",
            )
    raise HTTPException(status_code=404, detail="No report found for this id.")


# ---------------------------------------------------------------------------
# Helper: extract per-stock reports produced in THIS turn only
# ---------------------------------------------------------------------------

def _extract_this_turn_reports(messages: list) -> list[StoredReport]:
    """Return ALL per-stock reports generated in the current turn (possibly []).

    Scope: only messages that appear AFTER the last HumanMessage in the thread,
    so a report from a previous turn is never re-surfaced as if produced now
    (guards the AC-D3 two-layer invariant).

    Aggregation: the create_react_agent ToolNode may execute several
    generate_report tool calls in a SINGLE turn (one ToolMessage each). We scan
    EVERY this-turn ToolMessage whose JSON payload has a "reports" list, flatten
    every per-stock report dict across ALL of them, and de-duplicate by
    ``report_id`` (first occurrence wins, order preserved). This guarantees no
    per-stock report is dropped or overwritten when the LLM mistakenly issues one
    generate_report call per stock instead of one call with all stocks. Reading
    from the completed agent result (rather than racing inside the tool) is the
    concurrency-safe collection point.
    """
    import json
    from langchain_core.messages import HumanMessage, ToolMessage

    # Find the index of the last HumanMessage (this turn's user input).
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    this_turn_messages = messages[last_human_idx + 1:]

    out: list[StoredReport] = []
    seen_ids: set[str] = set()
    for msg in this_turn_messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            payload = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict) or "reports" not in payload:
            continue
        raw_reports = payload.get("reports")
        if not isinstance(raw_reports, list):
            continue
        for rep in raw_reports:
            if not isinstance(rep, dict):
                continue
            try:
                stored = StoredReport(
                    report_id=rep["report_id"],
                    title=rep["title"],
                    symbol=rep["symbol"],
                    markdown=rep["markdown"],
                )
            except (KeyError, TypeError):
                continue
            if stored.report_id in seen_ids:
                continue
            seen_ids.add(stored.report_id)
            out.append(stored)

    return out
