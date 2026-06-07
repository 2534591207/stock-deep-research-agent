from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


RunStatus = Literal["pending", "running", "completed", "partial", "failed"]
StepStatus = Literal["pending", "running", "completed", "partial", "failed"]


class Company(BaseModel):
    name: str
    symbol: str
    exchange: str
    aliases: list[str] = Field(default_factory=list)


class TimeRange(BaseModel):
    label: str
    start_date: date
    end_date: date
    source: Literal["user_explicit", "system_default"]


class ResearchTask(BaseModel):
    intent: str
    companies: list[Company]
    time_range: TimeRange
    focus: list[str]
    defaults_applied: list[str] = Field(default_factory=list)


class UploadedDocument(BaseModel):
    name: str
    content_base64: str


class RunRequest(BaseModel):
    query: str = Field(min_length=1)
    documents: list[UploadedDocument] = Field(default_factory=list)


class StepState(BaseModel):
    key: str
    label: str
    status: StepStatus = "pending"
    detail: str = ""


class StockRunState(BaseModel):
    company: Company
    status: RunStatus = "pending"
    steps: list[StepState]
    result: Optional[dict] = None
    warnings: list[str] = Field(default_factory=list)


class RunState(BaseModel):
    run_id: str
    query: str
    status: RunStatus = "pending"
    message: str = ""
    task: Optional[ResearchTask] = None
    stocks: dict[str, StockRunState] = Field(default_factory=dict)
    document_results: list[dict] = Field(default_factory=list)
    comparison: Optional[dict] = None
    report_markdown: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
