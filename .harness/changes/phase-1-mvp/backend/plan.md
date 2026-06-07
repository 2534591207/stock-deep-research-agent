# Plan — phase-1-mvp / 后端（v2 · 契约硬化版）

> SDD 流程：Constitution → Specify → **Plan（本文）** → Tasks → Implement
> 依据：[`spec.md`](spec.md)、[`../PRD.md`](../PRD.md)；根本大法 [`../../../constitution.md`](../../../constitution.md)
> **核心不变量**：快照/结果/比较/报告**全部不可变 + 版本化**；新研究生成新 ID，旧版本保留；量化由代码算，LLM 只出意图与叙述。

技术选型：**Python + FastAPI**；LLM = **OpenAI**；行情 Twelve Data、事件 Tavily、申报 SEC EDGAR；文件 PyMuPDF。

---

## 1. 架构与依赖

```
api/         FastAPI 路由 + schema（无业务逻辑）
orchestrator/ 主 Agent：plan → 并行单股研究 → 校验汇总 → 比较 → 报告 → 会话状态 + 追问
services/    intent / resolver / metrics / risk / market_view / event_research / business_risk / document / report
providers/   market_data · news · filings（接口 + US 实现）；SymbolCatalog；MarketPolicy
stores/      内存：snapshot_store / result_store / report_store / asset_store / workspace_store
config.py / models.py
```
依赖单向：`api → orchestrator → services → provider 接口/stores`。services/orchestrator **只依赖接口**。

**复用边界（措辞已纠正，不再宣称"零改动"）**：`metrics/risk/market_view/report/orchestrator` 不直接依赖厂商；但代码中存在**美国市场假设**（252 交易日、USD、ET 日历、SEC filing 体系）。这些假设集中在 **`MarketPolicy`**（§7）。未来加市场 = 新增 provider + catalog + **一个新 MarketPolicy**；本期只实现 `USMarketPolicy`，目标是**不阻碍未来扩展**，而非"核心零改动"。

---

## 2. API 设计

研究是异步长流程（并行 + LLM），**创建 run + 轮询**。前端/任何客户端只靠这些接口。

| 方法 / 路径 | 作用 | 响应要点 |
|---|---|---|
| `POST /api/research` | 建 run | `{run_id, status, plan}` |
| `GET /api/research/{run_id}` | 轮询全状态 | `RunState`（含 `latest_answer`、每股结果摘要、comparison 摘要、report 状态，见 §4）|
| `POST /api/research/{run_id}/messages` | 追问 | **`202 {message_id, status}`**；快速答即时就绪、重跑类轮询 `RunState.latest_answer_status=ready` 后取（见 §3）|
| `POST /api/research/{run_id}/uploads` | 上传 | `{asset_id, filename, status}`（status=registered→见 §3 处理模型）|
| `GET /api/research/{run_id}/results/{result_id}` | 取单股完整结果 | `StockResult`（含组件 + lineage）|
| `GET /api/research/{run_id}/comparisons/{comparison_id}` | 取比较 | `ComparisonResult` |
| `GET /api/research/{run_id}/assets/{asset_id}` | 取资产/片段 + 上传状态 | `SessionAsset`（按 citation 定位）|
| `GET /api/research/{run_id}/snapshots/{snapshot_id}` | 取行情快照（日线，供走势图/归一化）| `MarketDataSnapshot` |
| `GET /api/research/{run_id}/report?format=markdown` | 当前报告 | **等价于** `GET /reports/{active_report_id}` |
| `GET /api/research/{run_id}/reports` | 列报告版本 | `[{report_id,version,scope_version,status,created_at}]`，**按 version 升序固定** |
| `GET /api/research/{run_id}/reports/{report_id}?format=markdown` | 取指定版本 | **历史报告不可变** |
| `GET /api/health` | 健康 | `{ok:true}` |

**API 语义封死**：
- 业务降级（某股失败）不是 HTTP 错误，体现在 `RunState`。
- **并发互斥**：同一 run 同时只允许一个 mutation（research/换scope/上传/重生成）；冲突返回 **`409 {error:"run_busy", active_op}`**（§3）。
- **无效 id**：`run_id`/`result_id`/`report_id` 不存在 → **`404 {error, detail}`**；格式非法 → `400`。
- `format` 仅支持 `markdown`（本期；PDF 见 §10 与 PRD）。
- 入参跟随用户语言；报告正文/结论枚举英文。

---

## 3. 运行生命周期 · 并发 · 上传处理

```
created → planning → researching(并行单股) → comparing → reporting → done
                                       └→ partial / failed（隔离，不阻塞其它股）
```
- 单股 = 独立 asyncio 任务，`gather` 并行；失败/超时捕获标记，不影响其它股。单股总超时 ~25s；事件每股 ≤ 2 轮。
- **并发模型（MVP，不做复杂队列）**：每个 run 维护一个 `active_op`；mutation 类请求（追问触发重跑、上传、改时间、重生成报告）**串行化**——进行中再来 mutation → `409 run_busy`（前端可重试）；纯读（GET）不受限。
- **追问响应语义（202 + 轮询）**：`POST /messages` 立即返回 `202 {message_id}`；快速动作（`answer_from_existing_state`）`latest_answer` 可即时就绪，重跑类（改时间/换股，10–30s）需轮询 `RunState.latest_answer_status=ready` 后取 `latest_answer`。
- **active_op 获取/释放**：初始研究、追问重跑、上传处理、报告生成**各自占用** `active_op`，开始时获取、完成或失败时释放；占用期间其它 mutation → `409 run_busy`。
- **上传处理模型（满足 AC-22/29）**：`POST /uploads` 立即登记（`registered`）并后台处理；`analyzed` 后**自动**生成该公司的新报告版本（确定，非"可能"）。lifecycle `registered → extracted → attached → analyzed`，**任意阶段可 `failed`**；无法归属公司 → `needs_clarification`（提示指定，不硬塞）或 `unattached`。进度经 `GET /assets/{asset_id}` 或 RunState 反映（**无独立 `/uploads` 接口，统一走 assets**）。
- **上传拒绝**：>10MB / 非 `application/pdf`·`text/plain`·`text/markdown` / 不支持格式 → `400/415` 并说明，不入库。

---

## 4. 数据模型（不可变 + 版本化 + 完整血缘）

> 单一 `valid:bool` 不够——改用**组件级 lineage + validity**；快照/结果/比较/报告全部带 id、不可变，新研究生成新 id。

### 4.1 快照（外部数据的不可变记录，可追溯）
```python
MarketDataSnapshot:  snapshot_id; symbol; provider; request_params; bars; quote
                     retrieved_at; data_as_of; market_policy; warnings; payload_hash
EventSearchSnapshot: snapshot_id; symbol; move_id; window{start,end}; provider; query
                     results:[EventEvidence]; retrieved_at; warnings; payload_hash   # ← per move/window
FilingSnapshot:      snapshot_id; symbol; cik; filing_form; accession_number; filing_date
                     excerpts:[FilingExcerpt]; retrieved_at; source_url; payload_hash
UploadAsset:         asset_id; filename; mime; size; upload_time; owner_company?
                     status   # registered|extracted|attached|analyzed|needs_clarification|unattached|failed
                     failed_stage?; reject_reason?
UploadExtraction:    extraction_id; asset_id; chunks:[{chunk_id, page_start, page_end, text}]; extracted_at
```
`EventEvidence{evidence_id, title, url, source, source_tier, published_at, retrieved_at, direction}`。

### 4.2 组件化研究结果（不可变内容；有效性在 Workspace 侧）
> **不可变内容**：Snapshot / Component / StockResult / Report 内容一经生成不再改。**失效不改它们**，而是在 Workspace（§8.1）标记 `invalidated_parts` 并重跑生成**新 id**；旧版本保留。组件**带 `component_id`**。
```python
Component (不可变):
    component_id; component_type   # market_metrics | observed_market_risk | event | business_risk | market_view
    payload; input_snapshot_ids; generated_at
StockResult (不可变):
    result_id; symbol; time_range; scope_version; generated_at
    components: {component_type: component_id}   # 含 market_metrics / observed_market_risk / event / business_risk / market_view
```
**有效性 = Workspace 侧记录**：`invalidated_parts:[InvalidatedPart]`（按 `component_id`）+ `result_ids{symbol: active_result_id}`。
> 例：上传只让某公司 `business_risk` 组件失效（其余组件仍是当前 active）；改时间让 metrics/observed_market_risk/event/market_view 全部需新组件、filing 可复用但标 `filing as-of`。

### 4.3 比较与报告（不可变内容；生命周期在 Workspace 侧）
```python
ComparisonResult (不可变): comparison_id; scope_version; stock_result_ids; generated_at; ranking; caveat
ReportVersion (不可变内容):  report_id; version; scope_version; comparison_id; stock_result_ids
                  asset_ids_used; citation_ids; sections; section_index:[ReportSectionIndex]; created_at
```
**报告生命周期状态不写在 ReportVersion 上**，而在 Workspace：`report_lifecycle{report_id: active | stale | superseded}` + `active_report_id`。历史报告内容不可变；切换的只是 Workspace 侧的 active 指针与状态。

### 4.4 运行/会话状态（前端可直接用）
```python
RunState:
    run_id; status; plan; active_op?            # 并发互斥；值见 §3
    latest_answer; latest_answer_status         # ready | pending（202 语义，见 §3）
    workspace_summary{current_companies,time_range,focus,scope_version}
    stocks:[{symbol, status, active_result_id,
             current_quote{price,quote_time,freshness,is_demo_data},
             metrics_summary, observed_market_risk_summary,
             normalized_series_ref, market_snapshot_id}]    # ← 前端走势图/当前价/风险所需
    comparison{comparison_id, ranking_summary}
    report{active_report_id, report_lifecycle, report_versions}   # lifecycle: active|stale|superseded
    assets:[{asset_id, type, status}]           # status: registered|extracted|attached|analyzed|needs_clarification|unattached|failed
    invalidated_parts:[InvalidatedPart]; warnings
```

### 4.5 基础与时间戳
`Bar{date, open, high, low, close, adjusted_close, adjustment_basis, volume}`、`Quote{symbol, price, quote_time, is_delayed, partial_market, source_provider, freshness, is_demo_data, demo_snapshot_id?}`、`CompanyIdentity{name,symbol,exchange,instrument,market}`、`MarketMetrics{…§6…, calculation_basis, source_snapshot_id}`、`Event{…, citation_ids}`、`BusinessRisk{category, summary, citation_ids, asset_id, filing_form, accession_number, filing_date}`。
**贯穿字段**：`retrieved_at · data_as_of · published_at · filing_date · accession_number · quote_time · upload_time · provider`。

---

## 5. 服务契约（[code]/[llm]/[adapter]）

- **IntentParser [llm]**：NL → 候选公司/时间表达/关注点（只听懂）。
- **CompanyResolver [code+catalog]**：候选 → `CompanyIdentity` via **SymbolCatalog**（§7 落地）。
- **MarketDataProvider [adapter]**：`get_quote`/`get_history` → `MarketDataSnapshot`（复权日线）；US=TwelveData。
- **MetricsCalculator [code]**：吃 snapshot.bars → `MarketMetrics`（§6 公式）。
- **RiskScorer + MarketViewEvaluator [code]**：纯函数，**严格按 §6**（公式只在 §6 / PRD §8，别处只引用）。
- **EventResearch [adapter+llm]**：每个 move 一个 `EventSearchSnapshot`；[llm] 打 direction 枚举（仅展示）；[code] **来源分级+去重（policy 带 version/fixture，LLM 不参与 confidence）** → Event Attribution Confidence。
- **BusinessRisk [adapter+llm]**：`FilingSnapshot`（10-K Item1A / 20-F Item3D）；[llm] 摘类并**挂 citation_ids**；取不到降级。
- **DocumentAnalyzer [code+llm]**：PyMuPDF → `UploadExtraction`（chunk+page）；[llm] 归属公司。
- **ReportGenerator [code+llm]**：结构化结果 → 英文 9 节 + `ReportSectionIndex` + citation_ids；[llm] 只叙述。
- **Orchestrator [code]**：流程 + 会话状态 + 追问路由（§8.3）+ 失效/重跑（§8.3.1）+ 并发互斥。

---

## 6. 确定性计算契约（封死；与 PRD §8 一致）

```
daily_returns[t] = adjusted_close[t] / adjusted_close[t-1] - 1
日波动率   = stdev(daily_returns, ddof=1)         # sample stdev（固定，测试夹具锁定）
年化波动率 = 日波动率 × sqrt(252)                  # 展示
Negative-day vol = sample_stdev(负收益日收益) × sqrt(252)；负收益日<2 → null + reason（不用字符串"N/A"）
最大回撤   = 区间内最高 adjusted_close → 其后最低 adjusted_close 最大跌幅
最大单日   = 选 abs(change) 最大者；输出保留 signed change；阈值 abs(change) < 2% → 无显著异动
Data Coverage = 实际有效日线 / 预期交易日（预期交易日用 USMarketPolicy 的 US exchange calendar；测试注入 fixed calendar）

vol_score=min(日波动率/0.05,1)×100; drawdown_score=min(|回撤|/0.30,1)×100
risk_score=vol_score×0.6+drawdown_score×0.4   # 仅排序
绝对等级(最严重优先,含边界)：日线<10或Coverage<0.8→Undetermined；vol≥.03或dd≤-.20→High；vol≥.015或dd≤-.10→Medium；else Low
return_threshold=0.05×sqrt(预期交易日/21)
Market View：缺数/日线<10/Coverage<0.8→Insufficient；风险High→Cautious；收益<-阈值→Cautious；收益>+阈值→Positive；else Neutral
```
- 内部统一 **decimal**，展示再转 percent；每指标带 `calculation_basis`。
- 单测：PRD §10 自洽样例反推（→ risk_score 50.4/medium/cautious）；覆盖**缺失数据 / 负收益日<2→null / 最大回撤 / 风险分数并列排名**。

---

## 7. 配置 · Catalog 落地 · MarketPolicy · Demo

**SymbolCatalog 落地（保证"任意美股/ADR，非固定"）**：
- 来源：Twelve Data `/stocks` 参考接口拉取美国交易所标的；**过滤**：保留 `country=US` 且 `exchange∈{NASDAQ,NYSE,…}` 与 ADR，**排除 OTC/粉单**。
- 缓存：本地快照（启动加载，每日刷新或一次性快照）；解析 = 代码对名单做精确/模糊匹配 + 中文别名表。
- 演示用固定 catalog 快照，保证可复现。

**MarketPolicy（集中美国市场假设）**：`USMarketPolicy{trading_days_per_year:252, currency:"USD", timezone:"ET", exchange_calendar, filings:"SEC"}`。代码读它，不散落硬编码。

```python
MAX_STOCKS=3; MAX_RANGE_DAYS=365; MAX_MOVES_PER_STOCK=3; EVENT_ROUNDS=2; SIGNIFICANT_MOVE_MIN_PCT=0.02
RISK_THRESHOLDS={...}; SOURCE_TIERS_VERSION="v1"; SOURCE_TIERS={high:[...],medium:[...],weak:[...]}   # 枚举 high|medium|weak（PRD"高可信/可信/弱相关"映射到此）
RECENT_MESSAGES_N=6; COMPRESSION_TOKEN_THRESHOLD=6000   # 默认；测试注入小值（§8.5）
```
环境变量：`TWELVE_DATA_API_KEY / TAVILY_API_KEY / SEC_USER_AGENT / OPENAI_API_KEY`。
**未配 Key → 演示数据**：所有此类数据带 `is_demo_data=true` + `demo_snapshot_id` + 强制 `warning`，前端必须显眼标注，不得当实时。

---

## 8. 会话式 Agent

### 8.1 Research Workspace（不可压缩丢失）
```python
ResearchWorkspace:
    workspace_id; scope_version
    current_companies; current_time_range; focus
    result_ids{symbol: active_result_id}; result_store(ref §4.2)
    comparison_id; active_report_id; report_versions; report_lifecycle{report_id: active|stale|superseded}; active_op
    uploaded_assets; evidence_index; user_decisions; warnings
    invalidated_parts:[InvalidatedPart]; pending_mutations
```
> 同一 symbol ≠ 同一结果（绑定 time_range + snapshot）。

### 8.2 Session Assets + Claim-Citation Linkage
所有**可追问事实强制带 `citation_ids`**：`Event.citation_ids`、`BusinessRisk.citation_ids`、`ReportSectionIndex.citation_ids`、`MarketMetrics.source_snapshot_id`、`SignificantMove.event_search_snapshot_ids`（per move，复数）。
```python
CitationSpan:
    citation_id; asset_id; content_ref
    source_type; source_title; url 或 file_name
    chunk_id?; span_start?/span_end?; page_start?/page_end?; line_start?/line_end?
    quote/snippet; published_at; retrieved_at; data_as_of
ReportSectionIndex:
    report_id; section_id; section_type   # observed_market_risk|related_events|business_risks|…
    heading; owner_company; item_type; item_order   # item_order 在 (report_id+owner_company+section_type) 内编号
    text_span_ref; citation_ids
```
> "阿里第二条风险" = `section_type=business_risks, owner_company=BABA, item_order=2` → 经 citation_ids 取原文/页码/链接，**不靠 LLM 猜**。

### 8.3 Followup Router（LLM 出意图，code 决策）
```python
FollowupIntent (LLM):
    action_candidate; raw_mentions; target_company_refs; target_section_type; target_item_order
    time_range_phrase; refresh_requested; upload_reference; report_version_ref; ambiguity_flags
ScopeDiff (code):
    added_companies; removed_companies; replaced_companies
    time_range_changed; focus_changed; upload_added; refresh_requested; report_version_ref
RerunPlan (code):
    actions:[research_market|research_events|research_filing|analyze_upload|recompute_comparison|generate_report|answer_from_existing]
    affected_symbols; invalidated_component_ids; reused_result_ids
    provider_call_budget_expected; new_report_policy; active_report_transition
```
**code 决策优先级（写死）**：
```
1 out_of_scope/unsupported/ambiguity → clarify_request 或 reject_out_of_scope
2 显式公司/时间 scope 变更           → rerun_changed_scope
3 upload mutation                    → analyze_upload + report 失效
4 显式更新报告                       → regenerate_report
5 请求缺失组件                       → supplement_missing_research
6 否则                               → answer_from_existing_state
```
**校验与兜底（铁律）**：LLM 提到的所有 symbol/report_id/item_order **必须经 workspace/catalog/report_index 校验**；校验失败**不猜**→ clarify 或如实"找不到"。LLM 输出 malformed JSON → 保守 code 解析 → 不行就 clarify_request；**绝不默认复用旧指标去回答"改时间"类问题**。

### 8.3.1 Invalidation Matrix（确定性 · 无模糊词 · 创建新实体）
失效 = 标 `invalidated_parts` + 重跑生成**新 component/result/comparison/report id**（旧版本保留 superseded）。复用 = 引用现有 result_id。

| 变化 | metrics | event | business_risk | comparison | report |
|---|---|---|---|---|---|
| 改 focus | 复用 | 复用 | 复用 | 复用 | 旧版 superseded，生成新 report（同结果集）|
| 增加股票 | 旧股复用；新股全研究 | 同 | 同 | 失效→新 comparison | 失效→新 report |
| 删除股票 | 旧股复用；被删移出 scope | 同 | 同 | 失效→新 comparison | 失效→新 report |
| 替换股票 | 留存股复用；新股全研究 | 同 | 同 | 失效→新 comparison | 失效→新 report |
| 改时间范围 | 失效→重取 | 失效→重取 | filing 复用但标 filing as-of；business_risk_component 失效→重摘 | 失效→新 comparison | 失效→新 report |
| 上传文件 | 复用 | 复用 | **仅该公司**失效→重摘 | 复用（不含 business risk 摘要时）| 失效→新 report |
| 更新到最新数据 | 失效→重取 | 失效→重取 | 失效→重取 | 失效→新 comparison | 失效→新 report |
| 重新生成报告 | 复用 | 复用 | 复用 | 复用 | 旧版 superseded，生成新 report |

```python
InvalidatedPart: component_id; component_type; owner_symbol; reason_code; invalidated_by; invalidated_at
```
**active report 状态机**：历史 report 永久可取且不可变；mutation 期间 `active_report_id` **仍指向旧版**但 `report_lifecycle[旧版]=stale`；新报告**成功后才切** active（旧版 → `superseded`）；生成失败**不覆盖** active，只加 warning。（统一枚举：`active | stale | superseded`）

### 8.4 四层记忆 + Context Assembly
```
1 Recent Messages   最近 RECENT_MESSAGES_N 轮原文（理解指代）
2 Conversation Summary  较早摘要——可压缩层
3 Research Workspace   §8.1 结构化事实——不可压丢、不可被 summary 覆盖
4 Session Assets       §8.2 按需读片段
```
每轮上下文 = `guardrails + 当前消息 + recent + summary + 相关 workspace + 相关 asset 片段`（ContextAssembler 组装）。

### 8.5 压缩：触发 · schema · 原子协议
- **触发**：`recent_messages_count > RECENT_MESSAGES_N` 或 `token_estimate > COMPRESSION_TOKEN_THRESHOLD`。
```python
ConversationSummary:
    generated_at; source_message_range
    user_decisions; rejected/deferred_stocks; recent_scope_changes
    unresolved_clarifications; plain_language_recap
```
- **原子协议**：① 从选定消息生成 summary → ② 校验 summary **不修改 workspace** → ③ 持久化 summary → ④ **才**截断 raw messages；**任一步失败 → 保留 raw messages、不删**。summary 与 workspace 冲突 → **workspace 优先**。
- **不可丢字段清单**（补全）：`current_companies · time_range · focus · scope_version · active_report_id · report_versions · report active/stale 状态 · uploaded_assets + processing status · result_ids · component-level validity · comparison_id · citation/section index refs · pending_mutations · warnings · user_decisions · rejected/deferred · data_as_of · source timestamps`。
- `content_ref` 生命周期：压缩后仍可 dereference（本期内存 store 持有，不随 raw messages 删除）。

### 8.6 降级
逐条落 PRD §14；任何失败不编造数据。

---

## 9. 关键取舍（argue）
1. **量化全代码、模型只解释** → 可复现/可单测（Constitution）。
2. **catalog 目录驱动 + MarketPolicy** → 任意美股/ADR 同一流程、不写死；加市场 = provider+catalog+policy，目标"不阻碍扩展"（不宣称零改动）。
3. **不可变 + 版本化 + 组件 lineage** → 历史报告/局部重跑不串版本；部分失效精确。
4. **run + 轮询 + 单 mutation 互斥** → 前端无关、避免状态竞争（MVP 不做复杂队列）。
5. **LLM 只出意图、code 校验一切 id** → 不让模型把"改时间"误判成复用旧指标。

### 9.1 风险面与缓解
| 风险 | 缓解 |
|---|---|
| 多轮追问数据串版本 | 不可变 + 版本化 + 组件 lineage；report active/stale 状态机 |
| LLM 误判追问 → 复用旧指标 | id 全校验、决策优先级写死、malformed → clarify |
| 压缩丢关键状态 | 不可丢字段清单 + 原子协议 + AC-23/28 |
| "固定 Demo" 被识破 | catalog 真实落地 + 非固定股票（MSFT/AMZN）回归 |
| 外部 API 抽风 | 重试 + 演示数据强标(`is_demo_data`) + 降级不编造 |
| 状态竞争 | 单 mutation 互斥 + `409 run_busy` |
| 金融数值不稳 | sample stdev / 复权 / 固定日历 / decimal / §10 自洽样例单测 |

## 10. 测试策略（Implement 阶段 TDD）
- 单元（重点）：§6 全公式 + 边界（缺数/负收益日<2→null/回撤/并列排名）；失效矩阵每行一个用例（生成新 id、旧版 superseded、reused 正确）。
- 服务集成：provider 注入 fake/录制；**AC-12 以 fake provider 调用计数=0 验证**。
- 会话：Followup Router 决策优先级用例；malformed LLM 输出→clarify；并发 mutation→409。
- 压缩：手动 + **自动触发**；summary 写失败不删 raw；summary 不覆盖 workspace；压缩后"第二条风险"走 ReportSectionIndex+citation。
- API：`POST→GET→messages→reports/{id}`；历史报告不可变；无效 id 的 status/error body 固定。
- 演示夹具：NVDA/BABA/INTC + **MSFT/AMZN 等非固定股票** 各跑通，证明非写死。

> **范围澄清**：本后端阶段**只交 Markdown 报告**；PDF 是后续（前端/导出阶段），PRD 已同步。
> Tasks（原子拆解）在本 Plan 通过后产出；Implement 强制 TDD：先写失败测试 → 最小实现 → 验证。
