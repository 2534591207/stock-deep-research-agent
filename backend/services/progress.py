"""services/progress.py — Thread-safe per-stage progress sink for report builds.

The report pipeline (services/report.py::build_report) runs inside a worker
thread (via asyncio.to_thread) for the streaming endpoint. To forward real
per-stage progress to the browser WITHOUT changing build_report's signature or
return value, we use a module-level contextvars.ContextVar as an optional sink.

  - The streaming endpoint sets ``report_progress`` to a callable BEFORE
    spawning the worker thread, so the copied context carries the sink into the
    worker (contextvars are copied by asyncio.to_thread / asyncio.create_task).
  - build_report calls ``emit_stage(...)`` around each pipeline stage.
  - When NO sink is set (plain /chat, unit tests), emit_stage is a silent no-op,
    so existing callers are entirely unaffected.

Event shape (one dict per stage transition):
    {"type": "stage", "symbol": <TICKER or "__batch__">,
     "stage": <stage-id>, "status": "start" | "done" | "error"}
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Callable, Optional

# The optional sink. Default None → emit_stage is a no-op.
report_progress: ContextVar[Optional[Callable[[dict], None]]] = ContextVar(
    "report_progress", default=None
)


def emit_stage(symbol: str, stage: str, status: str) -> None:
    """Emit one stage event to the current sink, if any.

    Reads the ``report_progress`` contextvar. When a sink is set, calls it with
    a compact stage-event dict. When no sink is set, this is a silent no-op so
    plain /chat and unit tests are unaffected. Never raises into the caller: a
    misbehaving sink must not break the report pipeline.
    """
    sink = report_progress.get()
    if sink is None:
        return
    try:
        sink({"type": "stage", "symbol": symbol, "stage": stage, "status": status})
    except Exception:  # noqa: BLE001 — progress must never break the build
        pass
