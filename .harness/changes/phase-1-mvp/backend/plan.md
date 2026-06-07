# Plan — phase-1-mvp / 后端

> SDD 流程：Constitution → Specify → **Plan（本文）** → Tasks → Implement
> 依据：[`spec.md`](spec.md)（做什么）· [`../PRD.md`](../PRD.md)（需求基线）
> 本文聚焦**怎么做**：架构、API、数据模型、确定性计算契约、技术选型。任务拆解（Tasks）在本文通过后产出。

技术选型：**Python + FastAPI**；LLM 用 **OpenAI**；行情 Twelve Data、事件 Tavily、申报 SEC EDGAR；文件解析 PyMuPDF。

---

## 1. 架构与依赖

```
api/         FastAPI 路由 + 请求/响应 schema（无业务逻辑）
orchestrator/ 主 Agent：plan → 并行单股研究 → 校验汇总 → 比较 → 报告 → 会话状态
services/    intent / resolver / metrics / risk / market_view / event_research / business_risk / document / report
providers/   market_data · news · filings（接口 + 实现）；SymbolCatalog
config.py / models.py / markets registry
```

依赖方向单向：`api → orchestrator → services → provider 接口`。services/orchestrator **只依赖接口**，不依赖具体厂商。

**复用边界**：随"换市场/换数据源"而变的只有 `providers/*` 实现 + `config` 的市场/目录配置；`metrics / risk / market_view / report / orchestrator` 全部市场无关（吃统一 OHLCV 与结构化结果）。→ 加市场（如大 A）= 新增 provider + `MARKETS` 配置，核心零改动。

## 2. API 设计

研究是异步长流程（10–30s，并行 + LLM），采用**创建 run + 轮询**模型，天然支撑 PRD §11 可见编排。

| 方法 / 路径 | 作用 | 请求 → 响应 |
|---|---|---|
| `POST /api/research` | 建 run，后台启动 | `{query}` → `{run_id, status, plan}` |
| `GET /api/research/{run_id}` | 轮询状态/部分结果 | → `RunState` |
| `POST /api/research/{run_id}/messages` | 会话追问 | `{query}` → `RunState` |
| `POST /api/research/{run_id}/uploads` | 上传文件 | multipart → `{file_id, filename, attached_to?}` |
| `GET /api/research/{run_id}/report?format=markdown` | 下载报告 | → `text/markdown` |
| `GET /api/health` | 健康 | → `{ok:true}` |

约定：业务降级（某股失败）不是 HTTP 错误，体现在 `RunState` 的该股 `status=failed`+`warnings`；API 入参跟随用户语言，报告正文/结论枚举英文。

## 3. 运行生命周期与并发

```
created → planning → researching(并行单股) → comparing → reporting → done
                                       └→ partial / failed（隔离，不阻塞其它股）
```
单股 = 独立 asyncio 任务，`gather` 并行；失败/超时被捕获标记，不影响其它股。每完成一阶段更新内存态，`GET` 即时可见。单股总超时 ~25s；事件检索每股 ≤ 2 轮。

## 4. 数据模型（Pydantic，对应 PRD §10）

`Quote`、`Bar`、`CompanyIdentity{name,symbol,exchange,instrument,market}`、`MarketMetrics`、`SignificantMove{type,date/range,change_pct,events,attribution_confidence}`、`Event{title,date,source,url,direction}`、`ObservedMarketRisk{annualized_vol,max_drawdown,negative_day_vol,largest_daily_move,vol_score,drawdown_score,risk_score,absolute_level,relative_rank,observation_period,data_coverage_ratio}`、`ShortTermMarketView{value,return_threshold_pct,reason}`、`BusinessRisk{category,summary,source}`、`SingleStockResult`、`Comparison`、`Report`、`RunState{run_id,status,plan,stocks:[StockRunState],comparison,report_ready,warnings}`。

## 5. 服务契约（[code] 确定性 / [llm] 理解 / [adapter] 外部）

- **IntentParser [llm]**：NL → `{company_candidates, time_range_label, focus}`（只听懂，不定代码）。
- **CompanyResolver [code+catalog]**：候选 → `CompanyIdentity` via SymbolCatalog 接口 + 别名表；未命中/歧义如实处理。
- **时间解析 [code]**：NL→明确起止；上限 1 年；未来/超范围报无数据。
- **MarketDataProvider [adapter]**（接口）：`get_quote`、`get_history`（拆股复权日线）；US 实现 = TwelveDataProvider；失败重试两次→缓存/收盘价降级并标注。
- **MetricsCalculator [code]**：§7 全部公式；市场无关。
- **RiskScorer + MarketViewEvaluator [code]**：纯函数，吃 MarketMetrics 吐结论，严格按 §7。
- **EventResearch [adapter+llm]**：围绕最大单日异动用 NewsProvider(Tavily) 检索；[llm] 打方向枚举（仅展示）；[code] 来源分级+去重→Event Attribution Confidence。
- **BusinessRisk [adapter+llm]**：FilingsProvider(SEC) 按发行人类型取 10-K Item 1A / 20-F Item 3.D；[llm] 摘类；取不到降级。
- **DocumentAnalyzer [code+llm]**：PyMuPDF 提取 + [llm] 归属公司；作补充证据不覆盖行情。
- **ReportGenerator [code+llm]**：结构化结果 → 英文 9 节报告；[llm] 只叙述，数值来自结构化结果；渲染 Markdown。
- **Orchestrator [code]**：串流程 + 会话状态 + 追问路由（三类）。

## 6. 确定性计算契约（必须与封版 PRD §8 一致）

```
区间收益率   = last_close/first_close - 1
日波动率     = stdev(daily_returns)               # 内部用于打分/阈值
年化波动率   = 日波动率 × sqrt(252)               # 展示
Negative-day vol = stdev(负收益日收益) × sqrt(252)  # 负收益日<2 → N/A
最大回撤     = 区间内最高收盘→其后最低收盘 最大跌幅
最大单日     = |单日涨跌|最大；<2% → 无显著异动
Data Coverage = 实际有效日线/预期交易日

vol_score      = min(日波动率/0.05, 1)×100
drawdown_score = min(|最大回撤|/0.30, 1)×100
risk_score     = vol_score×0.6 + drawdown_score×0.4         # 仅排序

绝对等级(最严重优先,含边界)：
  有效日线<10 或 Coverage<0.8 → Undetermined（不排名）
  日波动率≥0.03 或 回撤≤-0.20 → High
  日波动率≥0.015 或 回撤≤-0.10 → Medium ; else Low
RISK_THRESHOLDS={medium_vol:.015,high_vol:.030,medium_dd:.10,high_dd:.20}

return_threshold = 0.05 × sqrt(预期交易日/21)              # 用预期日数
Short-term Market View(最严重优先)：
  缺数/日线<10/Coverage<0.8 → Insufficient data
  绝对风险=High → Cautious
  收益 < -return_threshold → Cautious
  收益 > +return_threshold → Positive ; else Neutral
```
> 单测以 PRD §10 自洽样例反推校验（年化波动 42.3% → risk_score 50.4 / medium / cautious）。

## 7. 配置（集中、可配 = 复用落点）

```python
MAX_STOCKS=3; MAX_RANGE_DAYS=365; MAX_MOVES_PER_STOCK=3
EVENT_ROUNDS=2; SIGNIFICANT_MOVE_MIN_PCT=0.02
RISK_THRESHOLDS={...}; SOURCE_TIERS={high:[...],medium:[...],weak:[...]}
MARKETS={"US":{catalog, market_data_provider, news_provider, filings_provider, alias_map}}
```
环境变量：`TWELVE_DATA_API_KEY / TAVILY_API_KEY / SEC_USER_AGENT / OPENAI_API_KEY`。未配 Key → 行情走标注过的演示数据，不伪装实时。

## 8. 会话式 Agent：状态 · 资产 · 记忆 · 追问路由 · 增量重跑

> 本期最核心的 Agent 能力（落 PRD §12 + spec AC-16..24）。**不是聊天记录，是研究工作区的结构化事实。**

### 8.1 Research Workspace（会话状态 · 核心 · 不可被压缩丢失）
```python
ResearchWorkspace:
    workspace_id
    current_companies     # [CompanyIdentity]，支持名单内任意标的，非固定
    current_time_range
    focus
    stock_results         # {symbol: SingleStockResult}
    comparison
    active_report_id      # 当前报告版本
    report_versions       # [report_id...]
    uploaded_assets       # [asset_id...]
    evidence_index        # 已查事件/证据
    warnings
    invalidated_parts     # 局部失效标记（换股/改时间后 comparison/report 失效）
```
"哪些数据已查过、哪些已失效"由它记录，**不靠模型记忆、不可被摘要压丢**。

### 8.2 Session Assets（会话资产索引 · 大内容按需读取）
报告、上传文件、行情快照、事件证据、filing 摘要、报告历史版本都是资产，**不每轮全文进上下文**。
```python
SessionAsset:
    asset_id; type; title; owner_company; summary; citations; content_ref; created_at; version
```
追问引用时：从 workspace 知道有哪些资产 → 按 owner/类型定位 → 只读相关片段 → 引用文件名+页码/链接。本期内存实现，概念必须在。

### 8.3 Followup Router（每轮先判 action）
```text
answer_from_existing_state   # "重点看风险" / "阿里第二条风险"
supplement_missing_research  # "那段为什么跌"（没查过）→ 补一步
rerun_changed_scope          # 换股/改时间 → 局部重研究
regenerate_report            # "更新报告" → 基于最新状态出新版本
clarify_request              # 歧义 → 一个澄清问题
reject_out_of_scope          # "我要买哪个" → 安全拒答转风险/证据
```
增量重跑：换股只研究新股 + 复用旧股 + 重算比较/报告；改时间重取受影响股票（旧指标作废、标 invalidated）；上传文件只更新相关公司结论 + 出新报告版本，不重复取行情。

### 8.4 四层记忆 + Context Assembly（每轮上下文按需组装）
```text
1 Recent Messages      最近 N 轮原文（理解"它/刚才/第二条/重新生成"等指代）
2 Conversation Summary 较早对话摘要（用户决定、范围修改、认为不相关的证据）——可压缩层
3 Research Workspace   §8.1 结构化状态——确定事实，不可被摘要覆盖、不可压丢
4 Session Assets       §8.2 大内容索引——按需读片段
```
每轮喂给 LLM 的不是全历史，而是 ContextAssembler 组装：
```text
system guardrails + 当前用户消息 + recent messages + conversation summary + 相关 workspace 状态 + 相关 asset 片段
```

### 8.5 压缩触发（原则，不做复杂算法）
- 最近 N 轮保留原文；超阈值生成 conversation summary。
- 用户决定、范围修改、报告版本、上传文件、关键结论**必须写入结构化状态**。
- 原始大文件不进 summary；**summary 不能覆盖 structured state**；压缩后必须能通过 **AC-23** 恢复关键研究事实。

### 8.6 降级
逐条落 PRD §14；任何失败不编造数据。

## 9. 关键取舍（argue）

1. **量化全代码、模型只解释** → 可复现/可对账/可单测（PRD 原则一）。
2. **catalog/provider 用接口、目录驱动** → 支持名单内**任意**美股/ADR 走同一流程，**不写死固定股票/组合/句式**（PRD §12 通用股票能力）；换数据源也零改核心。多市场（如 A 股）本期不做，但抽象不挡路。
3. **run + 轮询** → 支撑可见编排、前端无关、最简稳；SSE 为后续优化。
4. **会话只内存态** → PRD §12，避免存储依赖。
5. **事件方向只展示** → 不污染数值结论（PRD §8.6）。

## 10. 测试策略（Implement 阶段 TDD）

- 单元（重点）：metrics/risk/market_view/显著波动/事件分级——纯函数+夹具，覆盖 §6 全公式与边界（含 PRD §10 自洽样例）。
- 服务集成：provider 用可注入 fake/录制响应。
- API 端到端：固定 query 跑 `POST→GET→report`，断言 spec.md AC-*。
- 演示夹具：NVDA/BABA/INTC 固定 query + 期望事实，作回归集。

> Tasks（原子拆解）在本 Plan 通过后产出。Implement 阶段强制 TDD：先写失败测试 → 最小实现 → 验证。
