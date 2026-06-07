from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .document_analyzer import analyze_documents
from .event_research import research_events
from .intent_parser import parse_research_task
from .market_data import MarketDataProvider
from .market_metrics import calculate_metrics, normalized_series, significant_moves
from .models import RunRequest, RunState, StepState, StockRunState
from .reporting import compare_results, generate_report


STEPS = [
    ("identity", "公司识别"),
    ("market", "行情与指标"),
    ("moves", "显著波动"),
    ("events", "相关事件"),
    ("conclusion", "研究结论"),
]


class ResearchOrchestrator:
    def __init__(self) -> None:
        self.market = MarketDataProvider()
        self.runs: dict[str, RunState] = {}
        self.lock = threading.Lock()

    def create_run(self, request: RunRequest) -> RunState:
        run_id = uuid.uuid4().hex[:12]
        state = RunState(run_id=run_id, query=request.query, message="正在理解研究任务")
        with self.lock:
            self.runs[run_id] = state
        threading.Thread(target=self._execute, args=(run_id, request), daemon=True).start()
        return state

    def get_run(self, run_id: str) -> Optional[RunState]:
        with self.lock:
            state = self.runs.get(run_id)
            return state.model_copy(deep=True) if state else None

    def _execute(self, run_id: str, request: RunRequest) -> None:
        try:
            self._update_run(run_id, status="running", message="正在生成研究计划")
            task = parse_research_task(request.query)
            stocks = {
                company.symbol: StockRunState(
                    company=company,
                    steps=[StepState(key=key, label=label) for key, label in STEPS],
                )
                for company in task.companies
            }
            self._update_run(run_id, task=task, stocks=stocks, message=f"已创建 {len(stocks)} 个并行股票研究任务")

            documents = analyze_documents(request.documents)
            self._update_run(run_id, document_results=documents)

            results = []
            with ThreadPoolExecutor(max_workers=len(stocks)) as executor:
                futures = {executor.submit(self._research_stock, run_id, company, task): company.symbol for company in task.companies}
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        self._fail_stock(run_id, symbol, str(exc))
                        results.append({"company": stocks[symbol].company.model_dump(), "warnings": [str(exc)]})

            result_by_symbol = {result["company"]["symbol"]: result for result in results}
            ordered_results = [result_by_symbol[company.symbol] for company in task.companies]
            comparison = compare_results(ordered_results)
            report = generate_report(task, ordered_results, comparison, documents)
            status = "completed" if all(item.get("market_metrics") for item in ordered_results) else "partial"
            self._update_run(
                run_id,
                status=status,
                message="研究完成，综合报告已生成",
                comparison=comparison,
                report_markdown=report,
            )
        except Exception as exc:
            self._update_run(run_id, status="failed", message=str(exc), warnings=[str(exc)])

    def _research_stock(self, run_id: str, company, task) -> dict:
        self._set_step(run_id, company.symbol, "identity", "completed", f"已锁定 {company.name} ({company.symbol})")
        self._set_stock_status(run_id, company.symbol, "running")

        self._set_step(run_id, company.symbol, "market", "running", "正在获取行情并计算指标")
        market = self.market.get_history(company, task.time_range)
        metrics = calculate_metrics(market["bars"])
        normalized = normalized_series(market["bars"])
        self._set_step(run_id, company.symbol, "market", "completed", f"已获得 {len(market['bars'])} 个交易日数据")

        self._set_step(run_id, company.symbol, "moves", "running", "正在识别显著波动")
        moves = significant_moves(market["bars"])
        self._set_step(run_id, company.symbol, "moves", "completed", f"已识别 {len(moves)} 个显著波动日")

        self._set_step(run_id, company.symbol, "events", "running", "正在检索相关公开事件")
        events, warnings = research_events(company, task.time_range, moves)
        event_status = "completed" if events else "partial"
        self._set_step(run_id, company.symbol, "events", event_status, f"已获得 {len(events)} 条事件证据")

        self._set_step(run_id, company.symbol, "conclusion", "running", "正在形成结构化研究结论")
        result = {
            "company": company.model_dump(),
            "period": task.time_range.model_dump(mode="json"),
            "market_metrics": metrics,
            "significant_moves": moves,
            "normalized_series": normalized,
            "events": events,
            "source": market["source"],
            "freshness": market["freshness"],
            "warnings": warnings + (["当前使用明确标注的演示数据。"] if market["is_demo"] else []),
        }
        self._set_step(run_id, company.symbol, "conclusion", "completed", "单股票研究完成")
        self._set_stock_result(run_id, company.symbol, result, result["warnings"])
        return result

    def _update_run(self, run_id: str, **changes) -> None:
        with self.lock:
            state = self.runs[run_id]
            for key, value in changes.items():
                setattr(state, key, value)

    def _set_stock_status(self, run_id: str, symbol: str, status: str) -> None:
        with self.lock:
            self.runs[run_id].stocks[symbol].status = status

    def _set_step(self, run_id: str, symbol: str, key: str, status: str, detail: str) -> None:
        with self.lock:
            stock = self.runs[run_id].stocks[symbol]
            for step in stock.steps:
                if step.key == key:
                    step.status = status
                    step.detail = detail

    def _set_stock_result(self, run_id: str, symbol: str, result: dict, warnings: list[str]) -> None:
        with self.lock:
            stock = self.runs[run_id].stocks[symbol]
            stock.result = result
            stock.warnings = warnings
            stock.status = "completed" if not warnings else "partial"

    def _fail_stock(self, run_id: str, symbol: str, error: str) -> None:
        with self.lock:
            stock = self.runs[run_id].stocks[symbol]
            stock.status = "failed"
            stock.warnings.append(error)
            for step in stock.steps:
                if step.status == "running":
                    step.status = "failed"
                    step.detail = error
