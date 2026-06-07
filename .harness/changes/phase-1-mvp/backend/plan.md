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
| `GET /api/research/{run_id}/report?format=markdown` | 下载**当前**报告（= active 版本）| → `text/markdown` |
| `GET /api/research/{run_id}/reports` | 列出报告版本 | → `[{report_id, version, created_at, active}]` |
| `GET /api/research/{run_id}/reports/{report_id}?format=markdown` | 取**指定版本**报告 | → `text/markdown` |
| `GET /api/health` | 健康 | → `{ok:true}` |

约定：业务降级（某股失败）不是 HTTP 错误，体现在 `RunState` 的该股 `status=failed`+`warnings`；API 入参跟随用户语言，报告正文/结论枚举英文。

## 3. 运行生命周期与并发

```
created → planning → researching(并行单股) → comparing → reporting → done
                                       └→ partial / failed（隔离，不阻塞其它股）
```
单股 = 独立 asyncio 任务，`gather` 并行；失败/超时被捕获标记，不影响其它股。每完成一阶段更新内存态，`GET` 即时可见。单股总超时 ~25s；事件检索每股 ≤ 2 轮。

## 4. 数据模型（Pydantic · 带 provenance 与时间戳 · 对应 PRD §10）

基础：`Bar{date,open,high,low,close,volume}`、`Quote{symbol,price,quote_time,is_delayed,partial_market,source_provider,freshness}`、`CompanyIdentity{name,symbol,exchange,instrument,market}`、`MarketMetrics{…§6…,calculation_basis}`、`Event{title,date,source,source_tier,url,direction,published_at,retrieved_at}`、`SignificantMove{type,date/range,change_pct,events,attribution_confidence}`、`ObservedMarketRisk{annualized_vol,max_drawdown,negative_day_vol,largest_daily_move,vol_score,drawdown_score,risk_score,absolute_level,relative_rank,observation_period,data_coverage_ratio}`、`ShortTermMarketView{value,return_threshold_pct,reason}`、`BusinessRisk{category,summary,source,filing_form,accession_number,filing_date,page}`。

**带 provenance 的研究结果**（同一 symbol ≠ 同一结果，必须绑定时间范围与数据快照）：
```python
StockResult:
    result_id; symbol; time_range
    market_data_snapshot_id; event_search_snapshot_id; filing_snapshot_id
    uploaded_asset_ids_used
    market_metrics; observed_market_risk; significant_moves; short_term_market_view; business_risks
    generated_at; data_as_of; source_provider
    valid: bool; invalidated_reason
```
**版本化报告**：`Report{report_id, version, created_at, sections, section_index:[ReportSectionIndex]}`（ReportSectionIndex 见 §8.2）。

**运行/会话状态**：
```python
RunState:
    run_id; status; plan
    workspace_summary        # current_companies / time_range / focus / scope_version
    stocks: [StockRunState]  # 每股 status + active_result_id
    comparison_id
    active_report_id; report_versions
    assets: [asset_id]; invalidated_parts; warnings
```
**贯穿的时间戳/来源字段**：`quote_time · market_data_as_of · source_provider · freshness · published_at · retrieved_at · filing_date · accession_number · upload_time · page`。

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
- **Orchestrator [code]**：串流程 + 会话状态 + 追问路由（§8.3 六类 action）+ 增量重跑与失效判定（§8.3.1）。

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
> 单测以 PRD §10 自洽样例反推校验（年化波动 42.3% → risk_score 50.4 / medium / cautious）。内部统一用 **decimal**、展示再转 percent；每个指标带 `calculation_basis`。

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
    scope_version             # 每次 scope 变更 +1（换股/改时间/改关注点）
    current_companies         # [CompanyIdentity]，支持名单内任意标的，非固定
    current_time_range
    focus
    stock_result_ids          # {symbol: active_result_id} ← 存带 provenance 的 result 引用
    results_store             # {result_id: StockResult}（§4，绑定时间范围+数据快照）
    comparison_id
    active_report_id          # 当前报告版本
    report_versions           # [report_id...]（当前会话内版本，非账号历史）
    uploaded_assets           # [asset_id...]
    evidence_index            # 已查事件/证据
    warnings
    user_decisions            # 用户已确认/拒绝/推迟的选择
    invalidated_parts         # 局部失效标记（含原因）
```
> **同一 symbol ≠ 同一研究结果**：结果按 `result_id` 存、绑定时间范围与数据快照（§4 `StockResult`），避免改时间/换股/上传后误用旧指标。"哪些已查、哪些已失效"由它记录，**不靠模型记忆、不可被摘要压丢**。

### 8.2 Session Assets（资产索引 + 可定位 citation · 大内容按需读取）
报告、上传文件、行情快照、事件证据、filing 摘要、stock_result、报告历史版本都是资产，**不每轮全文进上下文**。
```python
SessionAsset:
    asset_id
    asset_type     # report / upload / market_snapshot / event_evidence / filing_excerpt / stock_result
    owner_company; version; created_at; data_as_of
    content_ref    # 按需读取的位置（内存/文件）
    summary
    citation_spans: [CitationSpan]

CitationSpan:
    citation_id; source_type; source_title; url 或 file_name
    page_start / page_end; section_id; item_order
    quote / snippet; published_at; retrieved_at; data_as_of
```
报告章节可定位（支撑"第二条风险""来自哪一页"这类追问）：
```python
ReportSectionIndex:
    report_id; section_id; heading; owner_company
    item_order; text_span_ref; citation_ids: [citation_id]
```
追问引用：workspace 知道有哪些资产 → 按 owner/类型/section/item 定位 → 只读相关片段 → 引用文件名+页码/链接/时间。本期内存实现，概念必须在。

### 8.3 Followup Router（LLM 出意图候选，code 做最终决策）
**边界铁律：LLM 只产出意图候选，不做最终重跑决策。**
```text
LLM → FollowupIntent { action_candidate, mentioned_companies, time_range_phrase, focus, report_version_ref }
code → catalog resolve · 确定性时间解析 · diff 当前 scope(ScopeDiff) · 生成 RerunPlan · 标 invalidated_parts · 拥有 provider 调用
```
action 枚举：
```text
answer_from_existing_state · supplement_missing_research · rerun_changed_scope
regenerate_report · clarify_request · reject_out_of_scope
```
> 否则模型可能把"改成最近一年"误判成 answer_from_existing_state → 复用旧指标。**重跑与失效判定永远在代码。**

### 8.3.1 Invalidation Matrix（哪种变化让哪些结果失效）
| 变化 | 行情指标/显著波动/MarketView | 事件归因 | filing/Business Risk | comparison | report |
|---|---|---|---|---|---|
| 只改分析角度（重点看风险）| 有效 | 有效 | 有效 | 有效（可重组）| 重组/可选新版本 |
| 增加股票 | 旧股有效；新股全研究 | 同左 | 同左 | **失效** | **失效** |
| 删除股票 | 旧股有效；被删股移出 scope | 同左 | 同左 | **失效** | **失效** |
| 替换股票（INTC→AMD）| NVDA/BABA 有效；AMD 全研究 | 同左 | 同左 | **失效** | **失效** |
| 改时间范围 | **全失效**（重取）| **全失效** | 可复用但标 filing as-of | **失效** | **失效** |
| 上传文件 | 不失效 | 不失效 | **失效**（仅相关公司）| 可保留 | **失效**（出新版本）|
| 更新到最新数据 | **失效**（重取）| **失效** | 视情况 | **失效** | **失效** |
| 重新生成报告 | 不失效 | 不失效 | 不失效 | 不失效 | 出新版本 |

> 失效 = 标 `invalidated_parts` + 重跑对应部分；复用 = 直接引用现有 `result_id`。**不靠模型凭感觉。**

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

### 8.5 压缩触发 + 测试协议
- 最近 N 轮保留原文；超阈值 `compress_conversation()` 生成 conversation summary。
- **不可压缩丢失字段清单**（必须留在 structured state，summary 永不覆盖）：
  `current_companies · current_time_range · focus · scope_version · active_report_id · report_versions · uploaded_assets · stock_result_ids · stock_result validity · comparison_id · warnings · user_decisions · rejected/deferred stocks · data_as_of · source timestamps`
- 原始大文件不进 summary；**summary 不能覆盖 workspace**，冲突时 **workspace 优先**。
- **AC-23 测试协议**：完成一次研究 → 手动 `compress_conversation()`（删早期 raw messages，只留 summary+workspace+assets）→ 再问"研究哪几家 / 时间范围 / 阿里第二条风险 / 更新报告" → 断言答案**来自 structured state**，不依赖完整聊天记录。

### 8.6 降级
逐条落 PRD §14；任何失败不编造数据。

## 9. 关键取舍（argue）

1. **量化全代码、模型只解释** → 可复现/可对账/可单测（PRD 原则一）。
2. **catalog/provider 用接口、目录驱动** → 支持名单内**任意**美股/ADR 走同一流程，**不写死固定股票/组合/句式**（PRD §12 通用股票能力）；换数据源也零改核心。多市场（如 A 股）本期不做，但抽象不挡路。
3. **run + 轮询** → 支撑可见编排、前端无关、最简稳；SSE 为后续优化。
4. **会话只内存态** → PRD §12，避免存储依赖。
5. **事件方向只展示** → 不污染数值结论（PRD §8.6）。

## 10. 测试策略（Implement 阶段 TDD）

- 单元（重点）：metrics/risk/market_view/显著波动/事件分级——纯函数+夹具，覆盖 §6 全公式与边界（含 PRD §10 自洽样例；**缺失数据 / 负收益日<2→N/A / 最大回撤 / 风险分数并列排名** 等边界）。
- 服务集成：provider 用可注入 fake/录制响应。
- API 端到端：固定 query 跑 `POST→GET→report`，断言 spec.md AC-*。
- 演示夹具：NVDA/BABA/INTC 固定 query + 期望事实，作回归集。

> Tasks（原子拆解）在本 Plan 通过后产出。Implement 阶段强制 TDD：先写失败测试 → 最小实现 → 验证。
