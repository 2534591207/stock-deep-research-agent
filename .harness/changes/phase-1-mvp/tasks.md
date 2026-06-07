# Tasks — phase-1-mvp（后端）

> 依据：同目录 [`spec.md`](spec.md) / [`PRD.md`](PRD.md)。**后端优先，前端暂缓。**
> 原则：纵向切片、每个任务可独立验收；先设计后写码；实现与评审分开（评审走 `.harness/roles/reviewer.md`，独立 agent）。
> 验收编号 `A1/B2/...` 引用 spec §12。

---

## 执行顺序（纵向链路）

```
T0 地基 → T1 单股确定性核心 → T2 单股 API 闭环 → T3 事件研究(B)
       → T4 多股并行+比较 → T5 报告+下载 → T6 会话追问
       → T7 经营风险(B+)+上传 → T8 演示夹具+降级
```
停止规则：T1 未通不进 T4；核心（T1–T5）未稳不做 T7/T8 之外的美化。

---

## T0 · 地基（skeleton / config / models / provider 接口）
- 范围：项目骨架、`config.py`（§8 全部常量）、`models.py`（§6 全部 Pydantic）、`providers/` 三个**接口**（market_data / news / filings）+ `MARKETS` 注册表（仅装 US 占位）。
- 交付：可 import、`pytest` 跑空壳通过；无任何业务硬编码厂商名于 services。
- 验收：`MarketMetrics` 等模型可实例化；接口有类型签名；`python -c "import config, models"` 通过。

## T1 · 单股确定性核心（指标 + 规则化结论）【核心，重测】
- 范围：`MetricsCalculator`、`RiskScorer`、`MarketViewEvaluator`、显著波动选取——全部 §7 公式。
- 交付：纯函数 + 单元测试夹具。
- 验收：**B1/B2/B3/B4**（含 PRD §10 样例反推自洽：risk_score≈50.4 / medium / cautious / return_threshold 动态）。
- 验证：`python -m unittest discover -s tests -v`（metrics/risk 全绿）。

## T2 · 单股 API 闭环（intent + resolver + market_data(US) + run）
- 范围：`IntentParser`(llm)、`CompanyResolver`(catalog+alias)、时间解析、`TwelveDataProvider`、`POST /api/research` + `GET /api/research/{id}` 跑通**单股**。
- 交付：单股 run 可创建、可轮询到含指标+结论的结果。
- 验收：**A1（单股部分）**；输入"分析英伟达最近三个月" → 锁定 NVDA/NASDAQ + 指标 + Observed Market Risk + Short-term Market View。
- 验证：起服务 `uvicorn app:app`，`curl POST/GET` 断言字段。

## T3 · 事件研究（B）
- 范围：最大单日异动 → `TavilyProvider` 检索（±窗口、≤2 轮、去重）→ 事件方向枚举(llm，仅展示)→ `EventAttributionConfidence`(code，来源分级)。
- 交付：单股结果带 events + attribution_confidence。
- 验收：**C1/C2**（无事件→该异动 Low，但仍出 Market View）。

## T4 · 多股并行 + 横向比较
- 范围：Orchestrator 并行（asyncio.gather）跑 ≤3 股、单股失败隔离；确定性比较 + 相对风险排名（带 caveat）。
- 交付：多股 run 完成，`GET` 返回各股状态 + comparison。
- 验收：**A1/A2/A3 + D1 + E2**（部分识别、超 3 只、失败隔离、排名 caveat）。

## T5 · 报告 + 下载
- 范围：`ReportGenerator`(llm 叙述 + code 数值) 出英文 9 节报告；`GET .../report?format=markdown`。
- 交付：可下载 Markdown 报告。
- 验收：**D2**（9 节齐全、来源、Observation period、英文免责、相对排名 caveat）。

## T6 · 会话与追问
- 范围：run 会话状态 + 追问三类路由（复用/重研究/补一步）。
- 交付：`POST .../messages` 可追问。
- 验收：**E1**（"重点比较风险"复用结果、不再调行情 provider）。

## T7 · 经营风险（B+）+ 上传（轻量核心）
- 范围：`SecEdgarProvider`（10-K Item 1A / 20-F Item 3.D 按发行人类型）+ llm 摘类（best-effort，取不到降级）；上传 PDF/TXT/MD 文本提取 + 归属。
- 交付：报告含 Business Risks（或降级提示）；上传作补充证据、标文件名+页码。
- 验收：**F1**；BABA 走 20-F 路径不报错。

## T8 · 演示夹具 + 降级
- 范围：未配 Key 的演示数据（明确标注）、各降级路径自测、固定 query + 期望事实回归集。
- 交付：无 Key 也能跑完整流程（标注演示数据）；降级路径覆盖。
- 验收：**E3** + PRD §17 演示可复现。

---

## 每个任务的收尾（harness 流程）
1. 自测：`python -m unittest discover -s tests -v` + 相关 `curl`。
2. `bash .harness/sensors/check-all.sh`。
3. 评审：独立 agent 走 `.harness/roles/reviewer.md`，对照本任务验收编号。
4. 通过后再进下一个任务。

> 前端：待样式确定后，作为后续变更（new change dir）单独规划；本期 API 即其稳定契约。
