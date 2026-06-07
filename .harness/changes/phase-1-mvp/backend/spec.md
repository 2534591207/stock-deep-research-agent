# Spec — phase-1-mvp（后端）

> 变更：`phase-1-mvp` · 依据：[`../PRD.md`](../PRD.md)（已封版，本 spec 不改其规则）· 前端见 [`../frontend/spec.md`](../frontend/spec.md)
> 范围：**后端（FastAPI）优先**；前端暂缓（仅约定 API 契约，任何客户端可驱动全流程）
> 角色分工铁律（PRD 原则一/二）：**量化指标由代码确定性计算，模型只理解/解释/提取；不算指标、不编造概率、不断言因果。**

---

## 1. 范围与非目标

**本期做（后端）**
- 一套 HTTP API，完整驱动 PRD 的研究闭环：理解请求 → 生成研究计划 → 多股并行研究 → 横向比较 → 生成可下载英文报告 → 当前会话追问。
- 确定性指标与规则化结论（PRD §6/§8）全部在代码里实现。
- 数据源接入：Twelve Data（行情）、Tavily（事件）、SEC EDGAR（经营风险，best-effort）。
- 上传文件文本提取作为补充证据（轻量核心）。

**本期不做**
- 前端样式/页面（API 之外）；账号系统、跨会话持久化；PDF 报告导出（先 Markdown）；OCR、向量库。

**非目标但架构必须不挡路**：未来可能接入美国以外市场（如 A 股）。因此市场标的目录、行情/新闻/申报数据源都走**接口 + 配置**，不在业务逻辑里写死 "US/Twelve Data"。本 spec 不展开多市场细节，只要求抽象边界干净（见 §11）。

---

## 2. 架构总览

```
HTTP (FastAPI)  ──  api/            路由 + 请求/响应 schema，无业务逻辑
                     │
Orchestration   ──  orchestrator/   主 Agent：plan → 并行单股研究 → 校验汇总 → 比较 → 报告 → 会话状态
                     │
Domain services ──  services/       intent / resolver / metrics / risk / market_view /
                     │               event_research / business_risk / document / report
                     │
Providers       ──  providers/      market_data · news · filings（接口 + 具体实现）
                     │
Config + Models ──  config.py / models.py（Pydantic）/ market registry
```

**依赖方向**：api → orchestrator → services → providers/接口。services 与 orchestrator **只依赖 provider 接口**，不依赖具体厂商。

**复用边界（关键）**：会随"换市场/换数据源"而变的，只有 `providers/*` 的具体实现 + `config` 里的市场/目录配置；`metrics / risk / market_view / report / orchestrator` 全部市场无关（吃的是统一的 OHLCV 与结构化结果）。

---

## 3. API 契约（后端即交付物）

> 研究是异步过程（10–30s，含 LLM + 并行取数）。采用**创建 run + 轮询状态**模型，天然支撑 PRD §11 的"可见编排"。

| 方法 / 路径 | 作用 | 请求 | 响应 |
|---|---|---|---|
| `POST /api/research` | 新建研究 run，后台启动 | `{ "query": "<自然语言>" }` | `{ run_id, status, plan }` |
| `GET /api/research/{run_id}` | 拉当前状态/部分结果（轮询） | — | `RunState`（见 §6） |
| `POST /api/research/{run_id}/messages` | 当前会话追问 | `{ "query": "<追问>" }` | 更新后的 `RunState` |
| `POST /api/research/{run_id}/uploads` | 上传补充文件 | multipart：file | `{ file_id, filename, attached_to? }` |
| `GET /api/research/{run_id}/report?format=markdown` | 下载报告 | — | `text/markdown`（本期；pdf 后续） |
| `GET /api/health` | 健康检查 | — | `{ ok: true }` |

**约定**
- `run_id` 唯一标识一次会话（PRD §12：单会话、内存态、不持久化）。
- `GET` 是幂等的状态读取；前端按需轮询（如 1s）即可呈现"研究计划 + 每股状态"。
- 错误用标准 HTTP code + `{ error, detail }`；业务降级（如某股失败）不是 HTTP 错误，而是体现在 `RunState` 的该股 `status=failed` + `warnings`（PRD §14）。
- 语言：API 入参跟随用户（中文）；报告正文英文；结论枚举英文（PRD §12）。

---

## 4. 运行生命周期与并发

```
created → planning → researching(并行单股) → comparing → reporting → done
                                                   └→ partial / failed（隔离，不阻塞其它股）
```

- `POST /api/research` 立即返回 `run_id` + 初步 `plan`，研究在后台任务（asyncio）里跑。
- 每只股票是一个独立异步任务，`asyncio.gather` 并行；单股失败/超时被捕获、标记，不影响其它股（PRD §14）。
- 每完成一个阶段就更新 run 的内存状态，`GET` 即时可见（驱动 §11 可视化）。
- 阶段超时：单股研究设总超时（如 25s）；事件检索每股 ≤ 2 轮（PRD §6）。

---

## 5. 领域服务契约

> 每个服务标注 **[code]**（确定性）/ **[llm]**（理解）/ **[adapter]**（外部）。LLM 不碰任何数值结论。

### 5.1 IntentParser **[llm]**
- in：用户自然语言；out：`ParsedIntent { company_candidates: [str], time_range_label, focus: [..] }`。
- 只做"听懂"：把中文/英文/别名归一成候选公司词 + 识别时间表达 + 关注点。**不决定代码/交易所**（交给 resolver）。

### 5.2 CompanyResolver **[code + catalog]**
- in：`company_candidates`；out：`[CompanyIdentity { name, symbol, exchange, instrument, market }]` + 未命中清单。
- 用**支持标的目录（SymbolCatalog 接口）** + 别名表裁决（PRD §5）。命中唯一→锁定；不在目录→如实未找到；歧义→标记需澄清。
- **市场无关**：catalog 是接口，US 用一个实现；换市场=换 catalog 配置。

### 5.3 时间解析 **[code]**
- 自然语言时间 → 明确 `start_date/end_date`（PRD §4 规则表）；硬上限 1 年；未来/超范围→报无数据。

### 5.4 MarketDataProvider **[adapter]**（接口）
- `get_quote(symbol) -> Quote`、`get_history(symbol, trading_days) -> [Bar]`（**拆股复权日线**）。
- US 实现 = `TwelveDataProvider`。返回统一 `Bar { date, open, high, low, close, volume }`，已复权。
- 失败：重试两次→缓存/收盘价降级并标注（PRD §14）；绝不编造。

### 5.5 MetricsCalculator **[code]**（核心，确定性）
- in：`[Bar]` + `expected_trading_days`；out：`MarketMetrics`（见 §7 公式契约）。
- 全部按 PRD §6/§8 公式：区间收益、日波动率、年化波动率、Negative-day volatility、最大回撤、最大单日、显著波动选取（阈值 2%）、Data Coverage。**市场无关。**

### 5.6 RiskScorer + MarketViewEvaluator **[code]**（规则化结论）
- 纯函数，吃 `MarketMetrics`，吐 `ObservedMarketRisk`（risk_score + absolute_level + 排名）与 `ShortTermMarketView`，**严格按 §7 公式与阈值**。模型不参与。

### 5.7 EventResearch **[adapter + llm]**
- 围绕每只股票的**最大单日异动**（默认只对它做归因，PRD §6），用 `NewsProvider`（Tavily）在异动日 ±窗口检索。
- `[llm]` 对每条事件打方向枚举 `positive/negative/neutral/unclear`（**仅展示，不进硬结论**，PRD §7）。
- `[code]` 按来源分级 + 去重，算 `EventAttributionConfidence ∈ {High,Medium,Low}`（PRD §8.3）。

### 5.8 BusinessRisk **[adapter + llm]**（B+ best-effort）
- `FilingsProvider`（SEC EDGAR）按发行人类型取 10-K Item 1A / 20-F Item 3.D（PRD §8.2）；`[llm]` 摘 top 3–5 类并标来源；取不到→降级为基于公开新闻的提示。不阻塞核心。

### 5.9 DocumentAnalyzer **[code + llm]**
- 上传 PDF/TXT/MD 文本提取（PyMuPDF/纯文本）；`[llm]` 归属到当前某公司；归不上→提示不硬塞。作补充证据，不覆盖行情（PRD §16）。

### 5.10 ReportGenerator **[code + llm]**
- 汇总结构化单股结果 → 英文综合报告（每股固定 9 节，PRD §13）；`[llm]` 只做叙述/解释，所有数值来自结构化结果。渲染 Markdown（PDF 后续）。

### 5.11 Orchestrator **[code]**
- 串起全流程 + 维护 run 会话状态 + 追问路由（PRD §12 三类：换角度→复用、换公司/时间→重研究、问缺失→补一步）。

---

## 6. 数据模型（Pydantic，对应 PRD §10）

`Quote`、`Bar`、`CompanyIdentity{name,symbol,exchange,instrument,market}`、`MarketMetrics`、`SignificantMove{type,date/range,change_pct,events,attribution_confidence}`、`Event{title,date,source,url,direction}`、`ObservedMarketRisk{annualized_vol,max_drawdown,negative_day_vol,largest_daily_move,vol_score,drawdown_score,risk_score,absolute_level,relative_rank,observation_period,data_coverage_ratio}`、`ShortTermMarketView{value,return_threshold_pct,reason}`、`BusinessRisk{category,summary,source}`、`SingleStockResult`、`Comparison`、`Report`、`RunState{run_id,status,plan,stocks:[StockRunState],comparison,report_ready,warnings}`。

> 字段与 PRD §10 的 JSON 结构一一对应，作为前后端/测试的稳定契约。

---

## 7. 确定性计算契约（必须与封版 PRD 完全一致）

```
区间收益率      = last_close / first_close - 1
日波动率        = stdev(daily_returns)              # 不年化（内部用于打分/阈值）
年化波动率(展示) = 日波动率 × sqrt(252)
Negative-day vol = stdev(负收益日的收益率) × sqrt(252)   # 负收益日<2 → N/A
最大回撤        = 区间内最高收盘→其后最低收盘 的最大跌幅
最大单日异动    = |单日涨跌| 最大者；< 2% → 视为无显著异动
Data Coverage   = 实际有效日线 / 预期交易日

vol_score      = min(日波动率 / 0.05, 1) × 100
drawdown_score = min(|最大回撤| / 0.30, 1) × 100
risk_score     = vol_score×0.6 + drawdown_score×0.4         # 仅排序

绝对等级(最严重优先，含边界)：
  有效日线<10 或 Coverage<0.8 → Undetermined（不参与排名）
  日波动率≥0.03 或 回撤≤-0.20 → High
  日波动率≥0.015 或 回撤≤-0.10 → Medium
  else → Low
RISK_THRESHOLDS = {medium_vol:.015, high_vol:.030, medium_dd:.10, high_dd:.20}  # 配置化

return_threshold = 0.05 × sqrt(预期交易日 / 21)            # 用预期日数，不因缺数下降
ShortTermMarketView(最严重优先)：
  缺数/日线<10/Coverage<0.8 → Insufficient data
  绝对风险=High → Cautious
  收益 < -return_threshold → Cautious
  收益 > +return_threshold → Positive
  else → Neutral
```

> 这些是实现层契约，**单元测试以 PRD §10 自洽样例反推校验**（例如：年化波动 42.3% → risk_score 50.4、absolute_level=medium、view=cautious）。

---

## 8. 配置（集中、可配，复用边界落点）

```python
MAX_STOCKS = 3
MAX_RANGE_DAYS = 365
MAX_MOVES_PER_STOCK = 3
EVENT_ROUNDS = 2
SIGNIFICANT_MOVE_MIN_PCT = 0.02
RISK_THRESHOLDS = {...}              # 见 §7
SOURCE_TIERS = { high:[...], medium:[...], weak:[...] }   # 来源域名分级
# 市场/目录/数据源以注册表方式装配（当前仅 US）：
MARKETS = { "US": { catalog, market_data_provider, news_provider, filings_provider, alias_map } }
```
环境变量：`TWELVE_DATA_API_KEY` / `TAVILY_API_KEY` / `SEC_USER_AGENT` / `OPENAI_API_KEY`。未配 Key → 行情走**明确标注的演示数据**，绝不伪装真实（PRD §14）。

---

## 9. 会话与追问

- run = 一次会话，内存态保存：公司、时间范围、关注点、各股结构化结果、已取证据、上传文件、当前报告。
- 追问三类按 PRD §12 路由：换角度→复用已有结果重组；换公司/时间→重研究；问缺失（如某段为何跌且没查过）→只补那一步检索。
- 关闭/刷新是否保留**不作核心验收**。

---

## 10. 错误与降级（落 PRD §14）

逐条映射为后端行为：无公司/跑题→提示；不在目录→如实未找到；部分可识别→识别的照做、其余标注；超 3 只→默认前 3 + 标注；超 1 年→默认 1 年；日线<10 或 Coverage<0.8→Undetermined/Insufficient；某股行情失败→隔离标 failed；Tavily 失败/无结果→保留行情、该异动 attribution=Low；上传冲突→提示不覆盖；Agent 超时→其它继续、报告标缺失。**任何失败都不编造数据。**

---

## 11. 关键设计取舍（深度 argue）

1. **为什么把量化全放代码、模型只解释** —— PRD 原则一。可复现、可对账、可单测；模型只碰自然语言（理解、归因措辞、报告叙述）。这是整套可信度的根。
2. **为什么 provider/catalog 用接口而非直接写 Twelve Data** —— 这是"不做死代码"的落点。换数据源或加市场（大 A 等）时，只新增 `providers/` 实现 + `MARKETS` 配置，`metrics/risk/report/orchestrator` 零改动。**本期只实现 US，但边界先留对。** 不在 spec 里展开多市场，避免过度设计；只要求依赖倒置干净。
3. **为什么 run + 轮询，而非一次性返回** —— 研究是多步并行长流程；轮询天然支撑 PRD §11"可见编排"，且前端无关、最简单稳。SSE/WebSocket 是后续优化，非本期必需。
4. **为什么会话只内存态** —— PRD §12 明确单会话、不跨会话持久化；内存 dict 足够，避免引入存储依赖。
5. **为什么事件方向只展示、不进硬结论** —— PRD §7/§8.6。否则模型主观会污染数值结论；硬结论全部来自代码规则。
6. **为什么先后端、前端缓** —— 样式未定；后端 API 是稳定契约，前端（甚至 curl）都能驱动验收。后端是价值与风险的核心。

---

## 12. 验收标准（后端/API 可测）

> 都能用 HTTP 调用或单元测试验证，不依赖前端。

**A. 理解与识别**
- A1 `POST /api/research {"query":"比较英伟达、阿里巴巴和英特尔最近三个月的表现"}` → `plan` 含 3 个锁定标的：NVDA/NASDAQ/common、BABA/NYSE/ADR、INTC/NASDAQ/common，时间范围解析为明确起止日。
- A2 含"小米"的多股请求 → 可识别的照常研究，小米标注"未找到美股标的"，不编码。
- A3 请求 5 只 → 默认取前 3，其余标注被推迟。

**B. 确定性指标（单测，带固定 bars 夹具）**
- B1 给定一组日线，`MarketMetrics` 的区间收益/日波动/年化波动/最大回撤/最大单日/Coverage 与手算一致。
- B2 `risk_score / absolute_level / ShortTermMarketView` 与 §7 公式一致；用 PRD §10 样例反推自洽（risk_score≈50.4、medium、cautious）。
- B3 Coverage<0.8 → Undetermined + view=Insufficient，且不参与排名。
- B4 最大单日 <2% → 标"无显著异动"，不强行找事件。

**C. 事件与归因**
- C1 围绕最大单日异动检索，返回事件含 时间/来源/链接/direction；按来源分级+去重得 attribution_confidence。
- C2 无可靠事件 → 该异动 attribution=Low，**整份研究仍出 ShortTermMarketView**（不变 Insufficient）。

**D. 比较与报告**
- D1 `GET /api/research/{id}` 在完成后返回横向比较（收益/波动/回撤 + 相对风险排名，标注"仅限本次所选股票与区间"）。
- D2 `GET .../report?format=markdown` 返回英文报告，每股 9 节齐全，含来源、Observation period、英文免责声明；相对排名带 caveat。

**E. 会话与降级**
- E1 追问"重点比较风险"→ 复用结果重组，不重新取数（可观测：不再调行情 provider）。
- E2 行情 provider 注入失败 → 该股 status=failed 隔离，其它股完成；报告标缺失。
- E3 未配 Key → 演示数据明确标注，不伪装实时。

**F. 上传**
- F1 上传文本 PDF → 提取成功、归属到某公司、报告标文件名+页码；与公开信息冲突时提示。

---

## 13. 测试策略

- **单元（重点）**：metrics / risk / market_view / 显著波动 / 事件分级——纯函数 + 固定夹具，覆盖 §7 全部公式与边界（含 §10 自洽样例）。
- **服务集成**：provider 用可注入的 fake/录制响应；intent/resolver 用固定输入断言结构化输出。
- **API 端到端**：用固定 query 跑 `POST → GET → report`，断言 §12 的 A/D/E。
- **演示夹具**：NVDA/BABA/INTC 的固定 query + 期望事实（公司身份、日期、算出的指标），作"能稳定复现"的回归集（PRD §17）。

任务拆解在 design 阶段之后产出。
