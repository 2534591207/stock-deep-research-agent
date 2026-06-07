from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from src.models import RunRequest
from src.orchestrator import ResearchOrchestrator


ROOT = Path(__file__).parent
app = FastAPI(title="Stock Deep Research Agent")
orchestrator = ResearchOrchestrator()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/styles.css")
def styles() -> FileResponse:
    return FileResponse(ROOT / "web" / "styles.css", media_type="text/css")


@app.get("/app.js")
def javascript() -> FileResponse:
    return FileResponse(ROOT / "web" / "app.js", media_type="application/javascript")


@app.post("/api/runs")
def create_run(request: RunRequest) -> dict:
    return orchestrator.create_run(request).model_dump(mode="json")


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    state = orchestrator.get_run(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    return state.model_dump(mode="json")
