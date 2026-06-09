# Tasks — phase-1-mvp / 后端（TDD 原子任务清单 · 两层对话 Agent 版）

> SDD 流程：Constitution → Specify → Plan → **Tasks（本文）** → Implement → Verify
> 本文**严格派生自已批准的 plan**（两层对话 Agent：顶层 `create_react_agent` + 下层按需报告编排 + 共用 services 内核；对外只有 `analyze_stocks` / `generate_report` 两个工具）。
> 依据（每个任务都必须回查）：
> - 需求基线：[`../PRD.md`](../PRD.md)（v6 两层架构）
> - 验收来源：[`spec.md`](spec.md) `AC-A1..A3 / B1..B6 / C1..C6 / D1..D3 / E1 / F1..F6 / G1..G2 / H1..H6`
> - 设计事实源：[`plan.md`](plan.md) §1–§14（目录 §3、工具契约 §5、services 契约 §6、报告编排 §7、API §9、config §10）
> - 根本大法：[`../../../constitution.md`](../../../constitution.md)
> - 设计门：plan 已通过负责人验收；本 Tasks 须经负责人**文档验收**后方可进入 Implement。

---

## 0. 本文档的契约与约束

### 0.1 状态
- 本文件是 Tasks 阶段产物，**文档先行**；任务体里的代码块只是**签名 / 夹具 / 断言意图示意**，不是实现。
- 验收通过才进入 Implement；Implement 强制 **TDD（先红后绿）**，每个 AC 有对应测试。

### 0.2 每个任务的固定结构
| 字段 | 含义 |
|---|---|
| **Objective** | 这个原子任务交付的业务能力（纵向闭环一环） |
| **Files** | 允许新建 / 修改的文件（实现期约束面，越窄越好） |
| **RED** | 先写、且必须先失败的测试（测试文件名 + 它断言什么） |
| **GREEN** | 让 RED 通过的最小实现要点（不超范围） |
| **Verification** | 通过判据（命令 + 期望产出） |
| **AC** | 覆盖的 `spec.md` 验收标准编号 |
| **Deps** | 前置任务 |

### 0.3 环境约束（已定）
- **运行环境 = Python 3.11**（本机 `python3.11`=3.11.15；已建仓库根 `/.venv`）。原因：本机默认 `python3` 是 3.9.6，`langgraph`(`create_react_agent`) 在 3.11 更稳，避免兼容坑。**实现与运行一律用 `.venv`（3.11）**。
- 依赖在 `backend/requirements.txt` 钉定（见 T0.1）；**不用 `python-dotenv`**——`pydantic-settings` 自带 `.env` 读取。
- `.env`（仓库根，含 4 个 key）/ `data/`（`us_catalog.json`）不受影响。

### 0.4 现状代码处理（务必作为 W0 任务，使新结构自包含可独立跑）
- 现有 `backend/` 是**旧 v2 手写实现**：`orchestrator/`、`api/`、`stores/`、`providers/`、旧 `tests/`（含 `unit/ integration/ session/ api/ smoke/`）、`util.py`、`manual_acceptance*.py`，以及旧 `services/` 里**新设计不用的文件**（`attribution.py`/`business_risk.py`/`document.py`/`event_research.py`/`intent.py`/`market_view.py`/`significant_moves.py`/旧 `comparison.py`）。
- **T0.1 负责清理 / 隔离旧 v2**：删除或移出上述旧模块，使新 app **不 import 任何旧模块**、新 `pytest` **不收集旧用例**。git 已留存旧版（可恢复），放心删。
- **可复用**：`backend/data/us_catalog.json`（旧 catalog，T2.2 resolver 可直接复用 / 适配）；`Dockerfile`/`docker-compose.yml`（P1 再用）。
- **覆盖重写**（旧文件存在但内容是旧设计，须按新 plan/spec 重写）：`config.py`、`models.py`、`services/{market_data,metrics,risk,resolver}.py`；**新增**：`services/{compare,time_range,report}.py`、`agent.py`、`tools.py`、`prompts.py`、`app.py`。

### 0.5 三个 plan 验收期 nit（必须在对应任务落实）
1. **nit① decimal/numpy**（落 T1.1）：指标底层用 **numpy/pandas float64 向量化**，关键输出 **round 到固定精度**做稳定断言；**不声称全 decimal 管线**（numpy 不支持 decimal 向量化）。AC-B1 容差取"浮点末位"。
2. **nit② time_range**（落 T1.4）：新增 `services/time_range.py`，把 `period` 自然语言 → 明确起止、默认 30 天、1 年封顶、注入固定 today、未来/无数据如实，承接 AC-H3。
3. **nit③ resolver 歧义**（落 T2.2）：`resolve()` 返回值区分 **found / none / ambiguous**（多匹配 → ambiguous 信号），让 agent 据此"只问一个澄清问题"，承接 AC-H4。

### 0.6 全局铁律（贯穿所有任务）
1. **用框架不造轮子**：agent 循环 = `create_react_agent`；记忆 = `MemorySaver`；LLM+工具 = `ChatOpenAI` + `@tool`；HTTP = FastAPI；配置/模型/校验 = pydantic + pydantic-settings；行情 = yfinance（Yahoo Finance，免费、无需 key、含 ADR/BABA、延迟/EOD）；数值 = numpy/pandas（不手撸 for 循环）；图 = matplotlib；报告排版 = Jinja2。**只手写「金融口径纯函数 + 薄编排胶水」。**
2. **两层不变量**：① `analyze_stocks` 永不出报告（`AnalyzeResult` schema 无 markdown 字段，结构性保证）；② `generate_report` 仅被明确要求时触发；③ 对外只有这两个工具；④ 所有数字只在 `services/` 纯函数算，LLM 不算数。
3. **诚实四原则**：数字交给代码 / 不断因果（只"可能相关"）/ 来源·时间·新鲜度透明（当前价标"延迟参考价、不用于交易"）/ 不构成投资建议。
4. **fail-fast 无 demo/mock**：缺核心 key 启动即 raise 列名（不打值），绝不伪造数据。
5. **金融公式与 spec §5.B 字字一致**；自洽样例全项目共用一套：`日波动率=0.02665, 最大回撤=−0.138, 区间收益=−0.104, 预期交易日=63 → vol_score=53.3, drawdown_score=46.0, risk_score≈50.4(50.38), Medium, return_threshold=0.0866, Cautious, 年化≈42.3%`。

### 0.7 验收金字塔
- **主**：fake provider + scripted/fake LLM 的**离线确定性验收**（可复现、调用计数可断言）。
- **辅**：**真实 smoke**（负责人本地，用 `.env` 的 `OPENAI_API_KEY`；行情 Yahoo Finance 免费无 key），对固定 + 非固定 ticker 跑通，证明联通线真实成立 + 通用；缺 key → `skip`，不打印 secrets。

---

## 1. 波次总览（纵向闭环，禁止逐层各写一半）

| 波次 | 名称 | 闭环产物 | 主要 AC |
|---|---|---|---|
| **W0** | 现状清理 + 骨架 + 依赖 + 配置/fail-fast | 旧 v2 隔离；新结构可 import；`pip install` 通过；`/health` 通；缺 key 启动 raise | AC-G1,G2（基建） |
| **W1** | 确定性内核（纯函数 · 重点 TDD · 无需 key） | `metrics`/`risk`/`compare`/`time_range` 全绿，自洽样例反推 | AC-B1..B6,C2..C5,H3 |
| **W2** | providers（取数 + 识别） | `market_data`（yfinance/Yahoo Finance，失败 raise）+ `resolver`（found/none/ambiguous，ADR 正确） | AC-F3,H1,H4,H5,H6 |
| **W3** | P0 对话闭环（工具 + agent + /chat） | `analyze_stocks` 薄封装 + `create_react_agent` + `MemorySaver` + `/chat`；离线 e2e 联通 | AC-A1..A3,B*,C1,C3,C4,C5,F2,H2 |
| **W4** | P0+ 报告 + ⑤⑥⑦ 节 + 引用 + 流式进度 | `generate_report` 编排（9 节+图+免责）+ `services/news.py`（Tavily）+ `services/sec.py`（SEC EDGAR）+ ⑤⑥⑦ 接入 report.py + 报告引用精确定位 + `POST /chat/stream` NDJSON 流式端点 + contextvar 进度 sink | AC-C6,D1..D4,E1,F1,F4,F5 |
| **W5** | 终验（联通线 + 通用性） | 离线全场景 e2e + 真实 smoke（固定 + 非固定 ticker） | 全量回归 + AC-H1 |
| **W6** | 文档上传 + RAG-lite 问答（纯增量） | `POST /upload` 通；`analyze_document` 四阶段流式全绿；现有 349 全绿（零回归） | AC-I1, AC-I2, AC-I3, AC-I4 |

> **停止规则**（PRD §15 / spec §5）：W1 确定性内核未全绿不进 W3 工具；W3 对话闭环（分析 + 比较，全程不出报告）未稳不进 W4 报告；W4 报告编排（含 ⑤⑥⑦ 节）未稳不进 W5 终验；P0 链路未稳不做 P1（流式/Docker）。

---

## W0 — 现状清理 + 骨架 + 依赖 + 配置 / fail-fast（地基）

### T0.1 现状分析 + 旧 v2 清理/隔离 + 新骨架 + 依赖钉定
- **Objective**：使**新结构自包含、可独立 import 与运行**；旧 v2 不再干扰；依赖在 Python 3.11 下装得上。
- **Files**：删/移 `backend/{orchestrator,api,stores,providers}`、`backend/services/{attribution,business_risk,document,event_research,intent,market_view,significant_moves,comparison}.py`、`backend/tests/`（旧树）、`backend/{util,manual_acceptance,manual_acceptance_app}.py`；新建空骨架 `backend/{app,config,agent,tools,prompts,models}.py`、`backend/services/{market_data,resolver,metrics,risk,compare,time_range,report}.py`、`backend/tests/`（新空树）；重写 `backend/requirements.txt`；`backend/.env.example`（只写 4 个 key 名）。
- **RED**：`tests/test_scaffold.py` —— `import app, config, agent, tools, prompts, models` 与 `services.{market_data,resolver,metrics,risk,compare,time_range,report}` 应成功（初为空模块）；断言全树**不触及任何旧模块名** → `grep -RInE "orchestrator|stores\.|providers\.|event_research|attribution|market_view|significant_moves|business_risk|intent" backend/*.py backend/services/*.py` 零命中。
- **GREEN**：清理旧文件；建空包/模块；`requirements.txt` 钉定（运行环境 Python 3.11）：`fastapi`/`uvicorn`/`langgraph`/`langchain-openai`/`langchain-core`/`pydantic`>=2/`pydantic-settings`/`pandas`/`numpy`/`matplotlib`/`jinja2`/`yfinance`/`httpx`/**`rapidfuzz`**(resolver 英文名模糊)/`pytest`/`pytest-asyncio`；在 `.venv`(3.11) 下 `pip install -r requirements.txt`。
- **Verification**：`.venv/bin/pip install -r backend/requirements.txt` 成功；`.venv/bin/python -c "from langgraph.prebuilt import create_react_agent; from langgraph.checkpoint.memory import MemorySaver; from langchain_openai import ChatOpenAI; import fastapi, pandas, numpy, jinja2, matplotlib, rapidfuzz, yfinance; print('OK')"` 打印 OK；`.venv/bin/pytest backend/tests/test_scaffold.py -q` 绿；grep 旧模块名零命中。
- **AC**：基建（间接支撑全部）。
- **Deps**：—

### T0.2 `config.py`（pydantic-settings + 常量 + require_keys）
- **Objective**：集中配置与常量；启动 key 校验 fail-fast。
- **Files**：`backend/config.py`。
- **RED**：`tests/test_config_failfast.py` —— monkeypatch 清空 `OPENAI_API_KEY`（验证缺失场景），调 `require_keys()` 抛错且消息**包含所有缺失 key 名、不含任何疑似真值**（AC-G1）；**核心只校验 `OPENAI_API_KEY`**（行情用 Yahoo Finance 免费无 key；`TAVILY_API_KEY` / `SEC_USER_AGENT` 缺失不触发启动失败，由对应 service 运行时降级）；另断言：清空 `TAVILY_API_KEY` 或 `SEC_USER_AGENT` 时 `require_keys()` **不抛错**（诚实降级不是启动失败）；常量值正确（`MAX_STOCKS=3`、`MAX_RANGE_DAYS=365`、`SIGNIFICANT_MOVE_MIN_PCT=0.02`、`TRADING_DAYS_PER_YEAR=252`、`RISK_THRESHOLDS`、权重 0.6/0.4、`RETURN_THRESHOLD_BASE=0.05`、`RETURN_THRESHOLD_REF_DAYS=21`、`MIN_EFFECTIVE_TRADING_DAYS=10`、`MIN_DATA_COVERAGE=0.80`、`MIN_NEGATIVE_DAYS_FOR_VOL=2`）。
- **GREEN**：`Settings(BaseSettings)` 读 env；`REQUIRED_KEYS` + `require_keys()`（缺则 `raise RuntimeError` 列名）；常量集中。
- **Verification**：`pytest tests/test_config_failfast.py -q` 绿；断言异常文本只含变量名、无 secrets。
- **AC**：AC-G1, AC-G2。
- **Deps**：T0.1

### T0.3 `app.py`（FastAPI + /health + startup fail-fast）
- **Objective**：可启动的 FastAPI；`/health` 不依赖 key/agent；startup 调 `require_keys()`。
- **Files**：`backend/app.py`。
- **RED**：`tests/test_health.py` —— `GET /health → 200 {ok:true}`；`tests/test_startup_failfast.py` —— 清空某核心 key 后启动（lifespan/startup）抛错列出缺失 key 名、进程拒绝启动（在第一个请求前），且**不提供任何 demo/mock 兜底**（AC-G2）。
- **GREEN**：装配 app + `/health` 路由 + startup 事件调 `require_keys()`；`/chat` 与报告端点在 W3/W4 接入。
- **Verification**：`pytest tests/test_health.py tests/test_startup_failfast.py -q` 绿。
- **AC**：AC-G1, AC-G2（启动语义）、基建。
- **Deps**：T0.2

> **W0 出口**：`pip install` 成功、新结构 import 干净（无旧模块）、`/health` 通、缺 key 启动 raise。未过不进 W1。

---

## W1 — 确定性内核（纯函数 · 重点 TDD · 无需 key）

> 这一波是产品护城河，**全部纯函数、脱离 agent 可单测**，用 spec §5.B 自洽样例反推。**LLM 不参与**。底层 numpy/pandas float64，关键输出 round 稳定断言（nit①）。

### T1.1 `services/metrics.py`（区间收益 / 波动 / 回撤 / 最大单日 / coverage / 归一化）
- **Objective**：snapshot bars → 全部确定性指标，公式严格按 spec §5.B。
- **Files**：`backend/services/metrics.py`（`compute_metrics`、`flag_significant_move`、`normalized_series`）。
- **RED**：`tests/test_metrics.py` —— 给一组**固定日线 fixture**，逐项手算对拍：
  - `daily_return[t] = adjusted_close[t]/adjusted_close[t-1] − 1`；`daily_volatility = stdev(daily_returns, ddof=1)`；`annualized = daily_volatility × √252`（AC-B1，逐项数值断言，float64 round 到固定小数）。
  - **AC-B2**：负收益日 < 2 → `negative_day_volatility = None + reason`（如 `insufficient_negative_days`），**非字符串 "N/A"**，且不影响其它指标。
  - `max_drawdown` = 区间最高 adjusted_close → 其后最低的最大跌幅（signed ≤ 0）；构造一个**全局最低点在全局最高点之前**的 fixture，断言朴素 `(max−min)/max` 会算错（保证"其后"约束）。
  - **AC-B3**：所有日收益 |幅度| < 2% → `flag_significant_move` 返回 `significant=false`；某日 |幅度| ≥ 2% → `true`（含边界 2% 取显著）。
  - `data_coverage = 有效日线 / 预期交易日`（注入固定预期交易日）。
  - `normalized_series`：起始日有价 → 该日 = 100.0；起始日无数据 → 窗口内**首个可交易日** close 为基准并注明 `normalized_base_date`。
- **GREEN**：numpy/pandas 向量化实现（无 for 循环做数组算术）；关键输出 round 固定精度。
- **Verification**：`pytest tests/test_metrics.py -q` 绿；该模块测试覆盖确定性分支（含上述边界）。
- **AC**：AC-B1, AC-B2, AC-B3（含归一化）。
- **Deps**：T0.1

### T1.2 `services/risk.py`（risk_score / absolute_level / short_term_market_view）
- **Objective**：metrics → 风险分数 + 绝对等级 + 短期市场观点，阈值规则严格按 spec §5.B。
- **Files**：`backend/services/risk.py`（`risk_score`、`absolute_level`、`short_term_market_view`）+ 读 `config.RISK_THRESHOLDS`。
- **RED**：`tests/test_risk.py` ——
  - **AC-B4 自洽样例（核心，逐项精确断言）**：`日波动率=0.02665, 最大回撤=−0.138, 区间收益=−0.104, 预期交易日=63` → `vol_score=53.3`（=min(0.02665/0.05,1)×100）、`drawdown_score=46.0`（=min(0.138/0.30,1)×100）、`risk_score≈50.4`（精确 50.38=53.3×0.6+46.0×0.4，断言 50.38 或 ±0.1 容差）、`absolute_level=Medium`、`return_threshold=0.0866`（=0.05×√(63/21)）、`short_term_market_view=Cautious`（因 −0.104 < −0.0866）。
  - **AC-B5 等级边界参数化（含边界、最严重优先）**：`(日波动=0.030, 回撤=0)→High`；`(0.015, 0)→Medium`；`(0.0149, 回撤=−0.10)→Medium`（回撤触发）；`(0.0149, −0.099)→Low`。
  - **AC-B6**：有效日线 < 10 或 coverage < 0.8 → `absolute_level=Undetermined`、`short_term_market_view=Insufficient data`。
- **GREEN**：三个纯函数；命中即停、最严重优先、阈值含边界（`≥` / `≤`）。
- **Verification**：`pytest tests/test_risk.py -q` 绿；断言"用预期交易日（非实际有效日）算 return_threshold"（防"少给数据更易判积极/谨慎"）。
- **AC**：AC-B4, AC-B5, AC-B6。
- **Deps**：T1.1

### T1.3 `services/compare.py`（横向比较 · 相对排名）
- **Objective**：多只统一口径 → 相对排名（纯代码），承接"比较在对话里、不出报告"。
- **Files**：`backend/services/compare.py`（`rank`）。
- **RED**：`tests/test_compare.py` ——
  - 按 `risk_score` 排相对名次（值越高风险越高，名次靠前）；
  - **AC-C2**：两只 `risk_score` 相等 → **并列同名次**；
  - **AC-C3**：只 1 只 → 返回 `None`（单股无比较语义）；
  - **AC-C4**：含 Undetermined 的不进排名，caveat 说明被排除；
  - **AC-C5**：结论**必带「仅限本次所选股票与区间」caveat**。
- **GREEN**：纯函数排名 + 并列 + 排除 + caveat。
- **Verification**：`pytest tests/test_compare.py -q` 绿。
- **AC**：AC-C2, AC-C3, AC-C4, AC-C5。
- **Deps**：T1.2

### T1.4 `services/time_range.py`（nit② · period 解析）
- **Objective**：自然语言 period → 明确起止；默认 30 天；1 年封顶；未来/无数据如实。
- **Files**：`backend/services/time_range.py`（`parse_period(text, today)`）。
- **RED**：`tests/test_time_range.py` ——
  - "最近三个月" → 90 自然日（代码规则）；
  - **AC-H3**：未给范围 → 默认最近 30 天，并返回可见说明文案；
  - "最近一年 / 超 1 年" → 截到 `MAX_RANGE_DAYS=365` + 超范围说明；
  - 未来日期 / 超出可用范围 → 如实返回"无数据 + 可用范围"；
  - **注入固定 `today`**（不使用真实时钟随机性，可复现）。
- **GREEN**：纯代码规则裁决（中文相对范围走代码分支；明确绝对日期可选 `dateparser`，非必须）。
- **Verification**：`pytest tests/test_time_range.py -q` 绿（注入固定 today）。
- **AC**：AC-H3。
- **Deps**：T0.1

> **W1 出口**：`metrics`/`risk`/`compare`/`time_range` 四个纯函数模块全绿，自洽样例反推通过。未过不进 W3 工具封装。

---

## W2 — providers（取数 + 识别）

### T2.1 `services/market_data.py`（yfinance/Yahoo Finance · 失败 raise · 延迟报价）
- **Objective**：`get_bars` / `get_quote` 取真实行情（拆股复权日线 + 当前参考价）；提供**录制 fake** 供离线测。
- **Files**：`backend/services/market_data.py`（`get_bars(symbol,start,end)->list[Bar]`、`get_quote(symbol)->Quote`、`FakeMarketData`（录制回放、`call_count`））。
- **RED**：`tests/test_market_data.py` ——
  - 注入录制数据 → `Bar{date,open,high,low,close,adjusted_close,volume}` / `Quote{price,quote_time,partial_market,source,freshness}` 字段齐全；
  - **取数失败 → raise**（不返回伪造数据，AC-F2 上游 / fail-fast）；
  - `Quote.partial_market = True`，带"延迟参考价、不用于交易"标注（AC-F3）；走势用已完成日线；
  - 无含息复权数据 → `calculation_basis = "split_adjusted"`，区间收益由上游标 **Price Return**；
  - `FakeMarketData.call_count` 可断言（为 AC-C6/调用计数铺路）。
- **GREEN**：yfinance（Yahoo Finance，免费无 key，`history(auto_adjust=True)`）封装；fake 录制回放。
- **Verification**：`pytest tests/test_market_data.py -q` 绿（fake/raise 路径）。
- **AC**：AC-F3（+ 为 AC-F2 铺路）。
- **Deps**：T0.1

### T2.2 `services/resolver.py`（nit③ · 别名 + ticker 直通 + 校验 · found/none/ambiguous）
- **Objective**：公司表达 → 标的身份；"支不支持"由名单裁决；歧义可识别。
- **Files**：`backend/services/resolver.py`（`resolve(text)->ResolveResult`，复用 `data/us_catalog.json` + `data/aliases.*`）。
- **RED**：`tests/test_resolver.py` ——
  - 英伟达 → `found: NVDA/NASDAQ/common`；
  - **AC-H5**：阿里巴巴 → `found: BABA/NYSE/ADR`，**绝不混 9988.HK**；instrument 正确区分 common/ADR；
  - **AC-H6**：小米 → `none`（未找到美股标的，**不编码**）；
  - **AC-H4**：一个会多匹配的输入 → `ambiguous`（带候选列表，供 agent"只问一个澄清问题"）；
  - **AC-H1**：MSFT / AMZN（非固定样本）→ `found`，证明不依赖固定股票。
- **GREEN**：三通道（精确 ticker 直通 / 英文名模糊（可用 `rapidfuzz`）/ 中文经别名表）→ 全落到同一份名单；**别名表仅便利通道、非支持边界**；返回 `ResolveResult{status: found|none|ambiguous, identity?, candidates?}`。本期名单 = ticker 直通（通用）+ 中文/英文别名 + 复用 `us_catalog.json`（curated，给 ADR/instrument）；真实性由 Yahoo Finance 取数校验；**全量离线 catalog 标 P1**。
- **Verification**：`pytest tests/test_resolver.py -q` 绿；断言 ambiguous 与 none 严格区分。
- **AC**：AC-H1, AC-H4, AC-H5, AC-H6。
- **Deps**：T0.1

> **W2 出口**：`market_data`（含 fake + 失败 raise）、`resolver`（found/none/ambiguous + ADR）全绿。

---

## W3 — P0 对话闭环（工具 + agent + /chat）

### T3.1 `models.py`（pydantic 结构化模型）
- **Objective**：落地工具输入/返回的结构化模型；**结构性保证 analyze 不出报告**。
- **Files**：`backend/models.py`（`CompanyIdentity`、`Bar`、`Quote`、`Metrics`、`Risk`、`StockAnalysis`、`AnalyzeResult`、`RankingResult`、`ResolveResult`、`ReportResult`、`ReportSectionItem`）。
- **RED**：`tests/test_models.py` —— 各模型实例化 + 字段校验；**断言 `AnalyzeResult` 不含 `markdown` / 下载字段**（结构上不可能出报告）；`StockAnalysis.status ∈ {ok, unrecognized, data_failed}`；`ResolveResult.status ∈ {found, none, ambiguous}`。
- **GREEN**：pydantic v2 模型（必要处 frozen）。
- **Verification**：`pytest tests/test_models.py -q` 绿；`grep -n "markdown" models.py` 在 `AnalyzeResult` 定义内无命中。
- **AC**：支撑 AC（结构性不变量）。
- **Deps**：T0.1

### T3.2 `tools.py::analyze_stocks`（@tool 薄封装 · 永不出报告）
- **Objective**：识别 1–3 只 → 取数 → 算指标/风险 → 多只比较；薄封装，自身无公式。
- **Files**：`backend/tools.py`（`analyze_stocks`）。
- **RED**：`tests/test_analyze_tool.py`（注入 `FakeMarketData`）——
  - 单只 → `AnalyzeResult.stocks[0]` 的 metrics/risk 数值正确（复用 W1）、`ranking=None`（AC-C3）；
  - 多只（2–3）→ 附 `ranking`（复用 compare）、带 caveat（AC-C1/C5）；
  - **断言返回对象无 markdown 字段 / 本轮无报告产物**（不出报告不变量）；
  - **AC-F2**：某只 `get_bars` 抛错 → 该只 `status=data_failed` 隔离、其余 `ok`、`warnings` 说明哪只失败、不伪造其数据；
  - **AC-H2**：> 3 只 → 取前 3 + `warnings` 标注其余被推迟；
  - **AC-F3**：当前价字段带"延迟参考价"标注；
  - **AC-H4**：某只 resolver 返回 ambiguous → `status=unrecognized` + 需澄清信息（供 LLM 只问一个）；
  - `period` 经 `time_range.parse_period` 解析（默认 30 天 / 1 年封顶，AC-H3 联动）。
- **GREEN**：薄封装：归一化入参 → `time_range`→`resolver`→`market_data`→`metrics`→`risk`→（多只）`compare` → 组 `AnalyzeResult`；**工具体无任何数值公式**。
- **Verification**：`pytest tests/test_analyze_tool.py -q` 绿（含调用计数：单纯分析不触发任何报告逻辑）。
- **AC**：AC-C1, AC-C3, AC-F2, AC-F3, AC-H2, AC-H4（+ 联动 H3）。
- **Deps**：T1.2, T1.3, T1.4, T2.1, T2.2, T3.1

### T3.3 `prompts.py` + `agent.py` + `app.py::/chat`（对话闭环 · 离线 e2e 联通）
- **Objective**：装配 `create_react_agent` + `MemorySaver` + `/chat`；离线证明"LLM→工具→service→回答"联通。
- **Files**：`backend/prompts.py`（SYSTEM_PROMPT）、`backend/agent.py`（`build_agent`）、`backend/app.py`（`/chat` 端点扩展）。
- **RED**：`tests/test_agent_chat.py` ——
  - **装配**：`build_agent()` 成功返回（`create_react_agent(model, tools=[analyze_stocks, generate_report], checkpointer=MemorySaver(), prompt=SYSTEM_PROMPT)`）；`tools` 恰为这两个。
  - **离线 e2e 联通**（核心）：用 **scripted/fake chat model**（发出一次对 `analyze_stocks` 的 tool_call）+ 注入 `FakeMarketData` → 跑一轮 → 最终回答里出现**代码算出的数值**（证明 LLM→工具→service→叙述全链路通）。【详述策略：fake chat model 用 `langchain_core` 的可脚本化假模型按预设发 tool_call；market_data 注入 fake；断言 tool 被调用且结果回流。】
  - **AC-A1**：scripted "你好/你能干嘛" → 模型不发 tool_call → **断言 tool-call 列表为空**、回复含"非投资建议"提示。
  - **AC-A2**：scripted "什么是波动率" → 不调工具。
  - **AC-A3**：scripted 非美股/跑题 → 不调工具、礼貌说明范围。
  - **记忆**：同 `thread_id=session_id` 连续两轮，第二轮"它"可指代第一轮股票（注入 fake 验证状态复用）。
  - **`/chat`**：`POST /chat {session_id,message}` → 200 `{reply}`；`reply` 取 `result["messages"][-1].content`。
- **GREEN**：`SYSTEM_PROMPT`（人设 + 诚实四原则"绝不自己算数一律走工具" + 何时调哪个工具 + 对话为核心报告按需 + 歧义只问一个）；`build_agent`；`/chat` invoke（`config={"configurable":{"thread_id":session_id}}`）。
- **Verification**：`pytest tests/test_agent_chat.py -q` 绿；离线 e2e 证明联通线（无需真实 key）。
- **AC**：AC-A1, AC-A2, AC-A3（+ 对话闭环/记忆基建）。
- **Deps**：T3.2, T0.3

> **W3 出口**：离线 fake 跑通"闲聊不调工具 / 分析 / 比较（不出报告）/ 记忆指代"；`/chat` 通。这是 **P0 达成标志**。未稳不进 W4 报告。

---

## W4 — P0+ 报告生成编排 + 引用

### T4.1 `services/report.py` + `services/image_host.py` + `tools.py::generate_report`（按需编排出每只独立 9 节英文报告）
- **Objective**：用户明说要报告时，逐只分析 → 汇总 → 比较 → 为**每只分别** Jinja2 组装 9 节报告 + matplotlib 图（图床上传或退回托管路径）+ 逐字免责；返回报告列表。
- **Files**：`backend/services/report.py`（编排 + Jinja2 模板 + matplotlib 渲染）、`backend/services/image_host.py`（GitHub Contents API 上传 PNG → URL；失败返回 None）、`backend/tools.py`（`generate_report`）。
- **RED**：`tests/test_report.py`（注入 `FakeMarketData`）——
  - 触发编排 → 逐只复用 `resolver/market_data/metrics/risk` + `compare`（数值与 W1 一致）；
  - **每只独立报告、9 节齐全**（断言每只产出独立 markdown，含节标题）：① Company Snapshot ② Price Trend（**归一化 base=100** + Price Return + 区间高低）③ Observed Market Risk（年化波动/负收益日波动/最大回撤/最大单日/risk_score/absolute_level/该批次相对排名+caveat/Data Coverage/Observation period）④ Significant Move ⑤ Related Events（**REQUIRED**；fake Tavily 返回事件时断言字段齐全：title/url/source/date/explanation/attribution_confidence；fake 返回空或 key 缺失时断言节内诚实注明，不抛错）⑥ Financial & Filing Highlights（**REQUIRED**；fake SEC 返回数据时断言含 form/date/sec_link；断言 CIK 动态解析、不硬编码；SEC 不可用时诚实注明）⑦ Business Risks（**REQUIRED**；fake SEC 返回时断言含逐字 title + source_url；无法提取时诚实注明）⑧ Short-term Market View（+非建议声明）⑨ Evidence & Limitations；
  - **AC-D2**：每份报告含与 spec §5.D / PRD §9 **逐字一致**的英文免责声明（字符串比对断言）；
  - **AC-F6（图床）**：注入 fake `image_host`（上传成功）→ Price Trend 节含 `raw.githubusercontent.com` URL；注入 fake `image_host`（返回 None / 失败）→ Price Trend 节退回后端托管路径，报告照常生成，不抛错；
  - 2 只时断言返回 `ReportResult.reports` 列表含 2 项（每项独立 `PerStockReport{report_id, symbol, title, markdown, download_ref}`）；`section_index` 跨两只合并。
- **GREEN**：普通顺序函数（无并发）；`image_host.upload(png, settings) -> str | None`（成功返回 raw URL，失败或配置缺失返回 None）；Jinja2 模板 + matplotlib `Agg` 渲染（CPU 渲染在异步路径用 `asyncio.to_thread` 包裹）；免责声明取自常量逐字。
- **Verification**：`pytest tests/test_report.py -q` 绿。
- **AC**：AC-D1（报告产物 · 每只独立）、AC-D2（免责逐字）、AC-F6（图床诚实降级）。
- **Deps**：T3.2

### T4.1a `services/news.py`（Tavily 客户端 + 事件证据组装 · ⑤ Related Events）
- **Objective**：封装 Tavily 检索；组装每条事件的必要字段；key 缺失或 API 失败时返回诚实降级结构（不抛错到上层）。
- **Files**：`backend/services/news.py`（`fetch_events(symbol, company_name, move_date, settings) -> EventsResult`）；`backend/requirements.txt`（加 `tavily-python`）。
- **RED**：`tests/test_news.py` ——
  - 注入 **fake Tavily 客户端**（返回预设条目）→ `EventsResult.items` 每条含 `title / url / source / date / explanation / attribution_confidence`；`explanation` 字段为描述性语言，断言不含「caused」「导致」等因果词；`attribution_confidence` 默认 `Low`；
  - **AC-F1 诚实降级**：fake 客户端返回空列表 → `EventsResult.degraded=True`，`degraded_reason` 含可读说明；
  - **AC-F1 key 缺失**：`TAVILY_API_KEY` 为空 → 函数**不抛错**，返回 `EventsResult.degraded=True`；
  - 断言 `attribution_confidence` 仅取 `"Low" | "Medium" | "High"`，默认 `"Low"`。
- **GREEN**：`tavily-python` SDK 调用；结构化返回；key 缺失 / 异常均走降级分支不上抛。
- **Verification**：`pytest tests/test_news.py -q` 绿（全离线 fake）。
- **AC**：AC-F1。
- **Deps**：T0.1

### T4.1b `services/sec.py`（动态 CIK + submissions + companyfacts + 10-K Item 1A · ⑥⑦）
- **Objective**：封装 SEC EDGAR HTTP 调用；动态解析 CIK；返回结构化申报记录 + 财务事实 + 风险标题；不可用时诚实降级。
- **Files**：`backend/services/sec.py`（`fetch_filings(cik, settings) -> FilingsResult`；`fetch_financials(cik, settings) -> FinancialsResult`；`fetch_risk_factors(cik, form_type, settings) -> RiskFactorsResult`；`resolve_cik(symbol, settings) -> str | None`）。
- **RED**：`tests/test_sec.py` ——
  - **AC-F4 动态 CIK**：注入 fake `company_tickers.json` → `resolve_cik("NVDA")` 返回正确 CIK 字符串；**断言代码中不含硬编码 CIK 字面量**（`grep -n "0001045810\|0001577552" backend/services/sec.py` 零命中）；
  - **AC-F4 申报记录字段**：fake `submissions` 响应 → `FilingsResult.filings` 每条含 `form / date / sec_link`；
  - **AC-F4 财务事实字段**：fake `companyfacts` 响应 → `FinancialsResult.facts` 含 source_link；
  - **AC-F5 风险标题逐字**：fake 10-K HTML → `RiskFactorsResult.risks` 每条含 `title`（原文逐字）+ `source_url`；断言 title 与 fake 文件内容字符串匹配（不是 LLM 改写）；
  - **AC-F4/F5 诚实降级**：`SEC_USER_AGENT` 为空 → 所有函数**不抛错**，返回对应 `*.degraded=True`；fake HTTP 500 → 同样降级；
  - `resolve_cik` 找不到 symbol → 返回 `None`（ADR 可能无 SEC filer，AC-F4 降级场景）。
- **GREEN**：`httpx` 同步调用（或 `asyncio.to_thread` 包裹）；`company_tickers.json` 本地缓存 + 按需刷新；10-K Item 1A 用 `html.parser` 定位风险因素标题（不手撸全文正则）；所有异常均走降级分支。
- **Verification**：`pytest tests/test_sec.py -q` 绿（全离线 fake）；grep 硬编码 CIK 零命中。
- **AC**：AC-F4, AC-F5。
- **Deps**：T0.1

### T4.1c `services/report.py` + `prompts.py` 接入 ⑤⑥⑦ 节
- **Objective**：把 `news.py` / `sec.py` 接入 `report.py` 的 ⑤⑥⑦ 节；更新 SYSTEM_PROMPT 说明 ⑤⑥⑦ 是必做节、降级时如何引用；更新 `section_index` 包含 ⑤⑥⑦ 条目供引用追问。
- **Files**：`backend/services/report.py`（接入 news/sec 调用 + Jinja2 模板扩展）；`backend/prompts.py`（SYSTEM_PROMPT 增加 ⑤⑥⑦ 引用规则）。
- **RED**：扩展 `tests/test_report.py` ——
  - 注入 fake news（有数据）→ 报告 ⑤ 节含事件条目，断言 title/url/source/date 字段在 markdown 中；
  - 注入 fake news（降级）→ 报告 ⑤ 节含诚实注明文字，节标题仍存在；
  - 注入 fake sec（有数据）→ 报告 ⑥ 节含 form/date/sec_link；⑦ 节含逐字 title + source_url；
  - 注入 fake sec（降级）→ ⑥⑦ 节各含诚实注明，不抛错；
  - `section_index` 含 ⑤⑥⑦ 的条目（`section="Related Events"` / `"Financial & Filing Highlights"` / `"Business Risks"`）。
- **GREEN**：report.py 顺序调用 `news.fetch_events` + `sec.fetch_filings/fetch_financials/fetch_risk_factors`；Jinja2 模板扩展 ⑤⑥⑦ 节（有数据 / 降级两种渲染分支）；section_index 扩展。
- **Verification**：`pytest tests/test_report.py -q` 绿（含新断言）。
- **AC**：AC-D1（9 节齐全含 ⑤⑥⑦）、AC-F1、AC-F4、AC-F5。
- **Deps**：T4.1, T4.1a, T4.1b

### T4.3 `POST /chat/stream`（NDJSON 流式端点）+ contextvar 进度 sink + ResearchProgress UI 协议
- **Objective**：为报告生成提供实时逐阶段进度流，使前端能为每只股票渲染「&lt;TICKER&gt; · Deep Research」进度卡片，固定流水线各阶段依次点亮；非报告轮次只输出一行 done 事件；同步 `/chat` 端点行为不变。
- **Files**：`backend/services/report.py`（在 `build_report` 各阶段入口/出口插入 contextvar sink 调用）、`backend/app.py`（新增 `POST /chat/stream` 路由，`StreamingResponse` + NDJSON 写出）。
- **RED**：`tests/test_chat_stream.py`（注入 `FakeMarketData` + scripted fake LLM）——
  - **AC-D4 报告轮次**：向 `POST /chat/stream` 发一条触发 `generate_report` 的请求 → 收集所有 NDJSON 行；断言：
    - 每行均为合法 JSON；
    - 每只股票按规范顺序出现十个 stage id（`identify` / `market_data` / `metrics` / `risk`；`compare` with `symbol="__batch__"`；`chart` / `events` / `filings` / `risk_factors` / `assemble`），每个 stage 各一次 `start`、一次 `done`；
    - `symbol` 字段对应正确 ticker（或 `"__batch__"` for compare）；
    - 最后一行类型为 `done`，含 `reply` 字符串与非空 `reports` 数组；
    - **不出现任何未定义 stage id**（断言 stage id 值在规范集合内）。
  - **AC-D4 非报告轮次**（闲聊 / 分析）：向 `POST /chat/stream` 发非报告消息 → 断言流中**无任何 stage 事件**，仅一行 `{"type":"done","reply":...,"reports":null}`。
  - **同步端点不变**：同一轮请求发到 `POST /chat` → 正常返回 `{reply, reports}`，无 NDJSON（证明两端点独立，AC-D4 注释）。
- **GREEN**：在 `services/report.py` 的 `build_report` 中用 `contextvars.ContextVar` 持有一个可选的进度回调；每个阶段入口/出口调用 `_emit(symbol, stage_id, status)`（sink 为 None 时静默跳过，保持 `/chat` 路径零开销）。`app.py` 中 `POST /chat/stream` 用 `StreamingResponse(media_type="application/x-ndjson")`：在 invoke 前把进度 sink 注入 contextvar，invoke 过程中实时 yield NDJSON 行，结束后 yield `done` 行。
- **Verification**：`pytest tests/test_chat_stream.py -q` 绿；`grep "chat/stream" backend/app.py` 命中；`grep "_emit\|progress_sink" backend/services/report.py` 命中（证明阶段埋点存在）；`POST /chat` 路径的现有测试（`test_agent_chat.py` / `test_report_cite.py`）仍全绿（无回归）。
- **AC**：AC-D4。
- **Deps**：T4.1, T4.1c, T4.2

### T4.2 报告引用闭环（section_index 存记忆 · 精确定位 · 不出报告不变量 · 报告列表端点）
- **Objective**：报告列表进会话记忆；引用某只某节某条精确定位；钉死"没要不出 / 比较不出"；暴露报告列表与单只下载端点。
- **Files**：`backend/prompts.py`（引用规则）、`backend/app.py`（报告端点：`GET /report/{session_id}`、`GET /report/{session_id}/{report_id}`、`GET /report/{session_id}/latest`）。
- **RED**：`tests/test_report_cite.py`（scripted LLM + fake）——
  - **AC-E1**：报告已生成（含多只 Business Risks），问"报告里阿里第二条经营风险" → 从 `section_index` 精确取 `owner_company=BABA, section=Business Risks, item=2` 那条复述 + 来源；**断言不误用其它股票、不编造**（走结构化索引）；
  - **AC-D1**：scripted "出一份报告"（2 只）→ 本轮 tool-call 含 `generate_report`、响应 `reports` 数组含 2 项（每项有 `report_id` / `title` / `symbol` / `download_ref`）；
  - **AC-D3**：scripted 只分析/比较、**没明说要报告** → **断言全程未触发 `generate_report`、`reports` 字段缺失**；
  - **AC-C6**：scripted 比较 3 只 → 走 `analyze_stocks`、**断言未触发 `generate_report`**；
  - `GET /report/{session_id}` → 200 `{reports:[{report_id, title, symbol}]}`；
  - `GET /report/{session_id}/{report_id}` → 200 `text/markdown`（单只报告可下载）；
  - `GET /report/{session_id}/latest` → 200 `text/markdown`（向后兼容）。
- **GREEN**：报告列表（`list[PerStockReport]`）随会话状态保留；SYSTEM_PROMPT 写明"引用走 section_index 精确读取、不猜"；三条下载端点。
- **Verification**：`pytest tests/test_report_cite.py -q` 绿。
- **AC**：AC-C6, AC-D1, AC-D3, AC-E1。
- **Deps**：T4.1, T3.3

> **W4 出口**：按需出报告（9 节+图+免责，⑤⑥⑦ 有数据路径与降级路径均全绿）、引用精确定位、"没要不出/比较不出"全绿、`POST /chat/stream` NDJSON 流十个规范 stage id 全绿（报告轮次与非报告轮次两路径）。**P0+ 达成。**

---

## W5 — 终验（联通线 + 通用性）

### T5.1 离线全场景 e2e（fake provider + scripted LLM）
- **Objective**：把 V1–V7 串成离线确定性回归，证明两层不变量与联通线。
- **Files**：`tests/test_e2e_offline.py`。
- **RED**：单文件覆盖：闲聊（工具计数=0）→ 单股分析 → 横向比较（**断言 `generate_report` 计数=0**）→ "出报告"（`generate_report` 计数=1）→ 引用报告某条精确 → 缺数据/识别失败诚实；**关键调用计数断言**贯穿（比较不出报告、闲聊不调工具）。
- **GREEN**：组合前序 fake/ scripted 设施，补端到端缺口（不重写前序模块）。
- **Verification**：`pytest tests/test_e2e_offline.py -q` 全绿。
- **AC**：AC-A*, B*, C*, D*, E1, F2, H* 综合（离线确定性）。
- **Deps**：W1–W4 全部

### T5.2 真实 smoke（负责人本地 · `.env` 真 key · 固定 + 非固定 ticker · 看效果关键）
- **Objective**：用真实 provider 跑通，证明联通线真实成立 + 通用（非写死）。
- **Files**：`tests/smoke/test_real_smoke.py`。
- **RED**：有 `OPENAI_API_KEY` 时（行情 Yahoo Finance 免费无 key，**含 BABA**）：对 **NVDA / BABA**（固定）+ **MSFT / AMZN**（非固定）各发起真实对话——识别→取真实行情→算指标→人话讲解；并对其中一组真实"出一份报告"→ 9 节英文报告可下载；**逐项结构断言**（identity 非空 / metrics 非空 / 报告 9 节齐 / 免责在）；**缺 key → `pytest.skip`**；**输出/日志不含 secrets**。
- **GREEN**：env-gated 真实驱动 + 结构断言 + 人工可核（落盘报告供肉眼看效果，不打印 secrets）。
- **Verification**：`cd backend && pytest tests/smoke/test_real_smoke.py -q`（负责人本地带 env）；缺 key→skip 计入；**`.env` 四 key 已齐，本步是"看效果"的关键验证**。另跑全量：`pytest -q`（离线全绿 + smoke skip/pass 如实）。
- **AC**：AC-H1（通用性）+ 真实联通佐证。
- **Deps**：T5.1

> **W5 出口**：离线全场景全绿 + 真实 smoke 跑通（固定 + 非固定 ticker）。**联通线证实、可看效果。**

---

## W6 — 文档上传 + RAG-lite 问答（纯增量 · 零回归）

> **铁律**：本波次全部改动为**纯增量**。W5 建立的 349 个测试（含离线 e2e + smoke）必须在 W6 全程保持全绿；任何回归立即停下查，绝不带着回归往下走。

### T6.1 `services/document.py` + `services/doc_store.py`（文本提取 + 切块 + 检索 + 摘要 · 离线确定性）
- **Objective**：实现文档处理纯函数与内存文档库；离线可测（fake embedder / fake llm 注入）；零改动现有 services。
- **Files**：`backend/services/document.py`（新）、`backend/services/doc_store.py`（新）、`backend/requirements.txt`（加 `pymupdf`）。
- **RED**：`tests/test_document.py` ——
  - `extract_text(data, filename)` PDF 夹具 → 返回 `DocText{text, pages, chars}`，`text` 非空；
  - `extract_text` TXT/MD 夹具 → 正确返回；
  - `extract_text` 扫描件夹具（无可提取文本）→ `raise`（诚实错误，不返回空文本），断言 raise 类型与消息含「OCR not supported」或同义；
  - `chunk_text(text)` → 返回列表，每块 ≤ `DOC_CHUNK_CHARS + DOC_CHUNK_OVERLAP`，块数 > 1（对足够长的文本）；
  - `embed_chunks(chunks, embedder=FakeEmbedder())` → 返回 `np.ndarray shape=(len(chunks), dim)`（离线确定性，FakeEmbedder 返回固定向量）；
  - `retrieve(question, doc, k=3, embedder=FakeEmbedder())` → 返回长度 ≤ k 的 `list[Excerpt]`，每个有 `text` 与 `locator`；余弦相似度正确（可用固定向量手算验证）；
  - `retrieve` 当 embedder 不可用（抛异常）→ 退化为关键词检索，不上抛，返回非空结果（诚实降级断言）；
  - `doc_store`：`put(session_id, doc)` → `get(session_id)` 返回同一文档；再 `put` 替换 → `get` 返回新文档；不同 `session_id` 互不影响。
- **GREEN**：PyMuPDF `fitz.open` 提取 PDF 文本；TXT/MD 直读；切块按 `DOC_CHUNK_CHARS` / `DOC_CHUNK_OVERLAP` 滑窗；`embed_chunks` 默认 `OpenAIEmbeddings(model=EMBEDDING_MODEL)`，可注入；`retrieve` numpy 余弦；`doc_store` 简单 `dict`；**零改动其他 service**。
- **Verification**：`pytest tests/test_document.py -q` 绿；`pytest -q`（全量，含 W0–W5 原有测试）绿（零回归）。
- **AC**：AC-I1（文本提取成功路径）、AC-I2（扫描件 raise）、AC-I3（retrieve 链路）。
- **Deps**：T0.1（骨架），T5.1（W5 全绿基线已确认）

### T6.2 `POST /upload`（新端点 · 不触碰任何现有端点）
- **Objective**：multipart 上传 → 校验 → 提取文本 → 存 doc_store → 返回元数据；三种错误路径诚实报错。
- **Files**：`backend/app.py`（新增 `POST /upload` 路由）。
- **RED**：`tests/test_upload.py` ——
  - 合法 PDF（可提取文本）+ 合法 `session_id` → `200 {filename, pages, chars, status:"ready"}`；`doc_store.get(session_id)` 非空；
  - 再次上传不同文件（同 `session_id`）→ `200`；`doc_store.get` 返回新文档（替换语义）；
  - 不支持扩展名（如 `.docx`）→ `415`，响应含可读说明；
  - 超过 `MAX_UPLOAD_MB` → `413`；
  - 扫描件（`extract_text` raise）→ `422`，响应含「OCR not supported」或同义说明；
  - **断言现有 `/chat` / `/health` / `/report/*` 端点行为不变**（对比请求各返回原样，调用计数不受影响）。
- **GREEN**：FastAPI `UploadFile` + `Form(session_id)`；调用 `document.extract_text` / `chunk_text` / `embed_chunks`（上传时即 embed）→ `doc_store.put`；捕获对应异常 → 对应 HTTP 状态码。
- **Verification**：`pytest tests/test_upload.py -q` 绿；`pytest -q` 全量绿（零回归）。
- **AC**：AC-I1, AC-I2。
- **Deps**：T6.1, T0.3

### T6.3 `tools.py::analyze_document` + `prompts.py`（第三工具 · 四阶段流式 · 纯增量）
- **Objective**：第三个 `@tool` 实现文档问答四阶段；更新 `prompts.py` 注入文档感知规则；`agent.py` 注册第三工具；现有两工具行为逐字节不变。
- **Files**：`backend/tools.py`（新增 `analyze_document`）、`backend/prompts.py`（增补文档规则，不删现有规则）、`backend/agent.py`（`tools=[..., analyze_document]`）。
- **RED**：`tests/test_doc_tool.py`（注入 `FakeDocStore` + `FakeEmbedder` + `fake llm`）——
  - 会话有文档：调用 `analyze_document("帮我分析风险")` → 返回 `DocumentResult{status:"ok", summary非空, excerpts非空}`；断言四个阶段事件按顺序被 emit（`doc_load` / `doc_parse` / `doc_locate` / `doc_summarize`，各 start/done，`symbol="__doc__"`）；
  - 会话无文档：返回 `DocumentResult{status:"no_document"}`；断言无阶段 emit；
  - 断言 `analyze_stocks` / `generate_report` 工具的签名与行为在同一测试进程中**零改动**（调用计数 / 返回结构与 W3/W4 测试一致）；
  - `prompts.py` 规则：断言 `SYSTEM_PROMPT` 包含「先简述文件…再回答」「文档中未提及」「不编造」等关键措辞。
- **GREEN**：`analyze_document` 工具体按 §5.3 契约实现；`prompts.py` 末尾追加文档规则段（不修改现有段落）；`agent.py` 在现有 `tools=[analyze_stocks, generate_report]` 后追加 `analyze_document`。
- **Verification**：`pytest tests/test_doc_tool.py -q` 绿；`pytest -q` 全量绿（零回归）；`grep "analyze_document" backend/agent.py` 命中；`grep "文档中未提及" backend/prompts.py` 命中。
- **AC**：AC-I3（工具流程 + 阶段 emit）、AC-I4（现有工具不变量）。
- **Deps**：T6.1, T6.2, T3.3

### T6.4 `/chat/stream` 文档轮次集成 + 前端文档轨协议验证
- **Objective**：端到端验证 `/chat/stream` 在文档轮次时正确输出 `__doc__` 阶段事件，并在非文档轮次零干扰；前端 `STAGE_LABELS` 协议文档更新。
- **Files**：`backend/tests/test_chat_stream.py`（扩展，不新建文件）；前端 `STAGE_LABELS` 协议更新（文档部分，若前端在范围内）。
- **RED**：在现有 `tests/test_chat_stream.py` 中追加两个用例——
  - **文档轮次**（scripted fake LLM 发出 `analyze_document` tool_call，fake doc_store 注入）→ 收集 NDJSON 行；断言：四个文档阶段事件按规范顺序出现（`doc_load` / `doc_parse` / `doc_locate` / `doc_summarize`，各 start/done，`symbol="__doc__"`）；**不出现任何股票报告阶段 id**；最后一行 `{"type":"done","reply":...,"reports":null}`；
  - **非文档轮次（分析 / 闲聊）**（与现有测试一致）→ 断言流中**无任何 `__doc__` stage 事件**，仅一行 done（AC-I4 流式验证）。
  - **现有报告轮次测试不变**：T4.3 建立的十个规范 stage id 测试仍全绿。
- **GREEN**：`analyze_document` 工具体内已正确 emit（T6.3）；`/chat/stream` 端点的进度 sink 消费逻辑对 `__doc__` symbol 已兼容（复用现有 contextvar 机制，无需改动 app.py 路由逻辑）。
- **Verification**：`pytest tests/test_chat_stream.py -q` 绿（含新增两用例 + 原有用例全绿）；`pytest -q` 全量绿（零回归）。
- **AC**：AC-I3（`__doc__` 流式阶段）、AC-I4（非文档轮次零干扰）、AC-D4（原有报告流式不变）。
- **Deps**：T6.3, T4.3

> **W6 出口**：`POST /upload` 三路径全绿；`analyze_document` 四阶段流式全绿；`/chat/stream` 文档轮次 + 非文档轮次两路径全绿；**全量 pytest（含 W0–W5 原有 349 测试）零回归**。文档功能纯增量，现有对话 + 报告链路逐字节不变。

---

## 2. AC ↔ Task 覆盖矩阵（证明 spec 全部 AC 有承接）

| AC | 主题 | 覆盖任务 |
|---|---|---|
| AC-A1 | 闲聊不调工具 + 非投资建议提示 | T3.3, T5.1 |
| AC-A2 | 解释概念不调工具 | T3.3 |
| AC-A3 | 跑题/非美股礼貌拒答 | T3.3 |
| AC-B1 | 指标手算对拍 | T1.1 |
| AC-B2 | 负收益日<2→null+reason | T1.1 |
| AC-B3 | 最大单日<2%→无显著异动 | T1.1 |
| AC-B4 | 风险自洽样例（53.3/46.0/50.38/Medium/Cautious） | T1.2 |
| AC-B5 | 绝对等级阈值边界 | T1.2 |
| AC-B6 | 日线<10/coverage<0.8→Undetermined/Insufficient | T1.2 |
| AC-C1 | 横向比较 + 相对排名 | T1.3, T3.2 |
| AC-C2 | risk_score 相同→并列 | T1.3 |
| AC-C3 | 单只不排名 | T1.3, T3.2 |
| AC-C4 | Undetermined 排除 | T1.3 |
| AC-C5 | 排名带「仅限本次所选股票与区间」caveat | T1.3 |
| AC-C6 | 比较全程不出报告（不变量） | T4.2, T5.1 |
| AC-D1 | 按需出每只独立 9 节英文报告可下载（报告列表） | T4.1, T4.2 |
| AC-D2 | 免责声明逐字 | T4.1 |
| AC-D3 | 没明说要报告→全程不出（不变量） | T4.2, T5.1 |
| AC-D4 | `POST /chat/stream` NDJSON 流：报告轮次十个规范 stage id start/done；非报告轮次仅 done 事件 | T4.3 |
| AC-E1 | 引用报告某条精确定位不串台 | T4.2 |
| AC-F1 | Related Events 诚实降级（Tavily 不可用 / 无证据时节内注明，不阻塞核心分析） | T4.1, T5.1 |
| AC-F4 | Financial & Filing Highlights：动态 CIK + SEC 字段 + 诚实降级 | T4.1b, T4.1c, T5.1 |
| AC-F5 | Business Risks：逐字标题 + source_url + 诚实降级 | T4.1b, T4.1c, T5.1 |
| AC-F6 | 图床不可用 → 走势图退回后端托管路径，报告照常生成 | T4.1 |
| AC-F2 | 单股行情失败隔离 | T2.1, T3.2 |
| AC-F3 | 当前价标「延迟参考价」 | T2.1, T3.2 |
| AC-G1 | 缺核心 key→启动 raise 只列名 | T0.2, T0.3 |
| AC-G2 | 绝不 demo/mock 兜底 | T0.2, T0.3 |
| AC-H1 | 非固定样本走完整流程 | T2.2, T5.2 |
| AC-H2 | >3 只→前 3 + 标注推迟 | T3.2 |
| AC-H3 | 未给时间→默认 30 天告知 | T1.4, T3.2 |
| AC-H4 | 歧义→只问一个澄清（resolver ambiguous） | T2.2, T3.2 |
| AC-H5 | 阿里→BABA·NYSE·ADR 不混 9988 | T2.2 |
| AC-H6 | 识别不了→如实说不编码 | T2.2 |
| AC-I1 | 上传成功→200 + {filename,pages,chars,status:"ready"} | T6.1, T6.2 |
| AC-I2 | 不支持类型/过大/扫描件→415/413/422，不做 OCR | T6.1, T6.2 |
| AC-I3 | 文档问答→`analyze_document`+四阶段 `__doc__` 流式+先总结+严格基于原文+"文档中未提及" | T6.1, T6.3, T6.4 |
| AC-I4 | 无文档或非文档问题→现有流程不受影响，`analyze_document` 不被调用 | T6.3, T6.4 |

> **覆盖校验**：spec 全部 AC（A1–A3 / B1–B6 / C1–C6 / D1–D4 / E1 / F1–F6 / G1–G2 / H1–H6 / **I1–I4**）均**至少一个任务承接**；AC-F1（Related Events 诚实降级）、AC-F4（Financial & Filing Highlights）、AC-F5（Business Risks）均为 P0+ 必做，承接于 T4.1a / T4.1b / T4.1c 任务；AC-F6（图床诚实降级）承接于 T4.1；AC-D4（`POST /chat/stream` NDJSON 流式进度）承接于 T4.3；**AC-I1–I4（文档上传 + RAG-lite 问答）承接于 T6.1–T6.4（W6 波次，纯增量）**。

---

## 3. 依赖拓扑（实现顺序，可并行点已标注）

```
W0: T0.1 → T0.2 → T0.3
W1: T0.1 →（T1.1 → T1.2 → T1.3） ；T0.1 → T1.4（与 T1.x 可并行）
W2: T0.1 →（T2.1, T2.2 并行）
W3: （T1.2, T1.3, T1.4, T2.1, T2.2, T3.1）→ T3.2 → T3.3（也依赖 T0.3）
W4: T3.2 → T4.1 → T4.1a（可与 T4.1b 并行）→ T4.1b → T4.1c → T4.2（也依赖 T3.3）；T4.1c → T4.3（也依赖 T4.2）
W5: 全部 → T5.1 → T5.2
W6: T5.1（W5 全绿基线） → T6.1 → T6.2 → T6.3 → T6.4
```
> **波次内纵向闭环优先；跨波禁止把所有 service/工具/agent 各写一半。W1 确定性内核先封口（纯函数 → 工具薄封装 → agent 装配 三层顺序）。W6 在 W5 全绿基线上纯增量叠加，任何 W0–W5 回归立即停。**

---

## 4. 测试目录约定（Implement 期建立）

```
backend/tests/
  test_scaffold.py            # T0.1 import 干净 + 无旧模块
  test_config_failfast.py     # T0.2 缺 key raise 列名
  test_health.py              # T0.3 /health
  test_startup_failfast.py    # T0.3 启动 fail-fast
  test_metrics.py             # T1.1 指标手算对拍 + 边界
  test_risk.py                # T1.2 自洽样例 + 阈值边界
  test_compare.py             # T1.3 排名/并列/排除/caveat
  test_time_range.py          # T1.4 period 解析（注入固定 today）
  test_market_data.py         # T2.1 fake/raise/partial-market
  test_resolver.py            # T2.2 found/none/ambiguous/ADR
  test_models.py              # T3.1 AnalyzeResult 无 markdown
  test_analyze_tool.py        # T3.2 工具：不出报告/隔离/边界
  test_agent_chat.py          # T3.3 离线 e2e 联通 + 闲聊不调工具
  test_news.py                # T4.1a fake Tavily：字段/降级/key缺失
  test_sec.py                 # T4.1b fake SEC：动态CIK/字段/降级/无硬编码
  test_report.py              # T4.1 + T4.1c 9 节（含⑤⑥⑦有数据/降级）+ 免责逐字
  test_report_cite.py         # T4.2 引用精确 + 没要不出 + 比较不出
  test_chat_stream.py         # T4.3 /chat/stream NDJSON：报告轮次十 stage / 非报告仅 done
  test_e2e_offline.py         # T5.1 全场景离线回归 + 调用计数
  smoke/test_real_smoke.py    # T5.2 真实 key smoke（固定+非固定）
  test_document.py            # T6.1 extract/chunk/embed/retrieve/doc_store（FakeEmbedder 离线）
  test_upload.py              # T6.2 POST /upload：成功/415/413/422 + 现有端点不变
  test_doc_tool.py            # T6.3 analyze_document 工具：四阶段 emit + no_document + 现有工具不变
  fixtures/                   # 固定日线 / 录制行情 / scripted LLM 响应 / PDF夹具（可提取文本 + 扫描件）
```
> 主：fake provider + scripted LLM 离线确定性（可复现、计数可断言）；辅：真实 smoke（`.env` 真 key，缺则 skip，不打印 secrets）。

---

## 5. 待负责人验收点（文档先行 → 才进 Implement）

1. **波次切分**（W0 清旧→W1 纯函数内核→W2 取数识别→W3 对话闭环→W4 报告引用→W5 终验）是否认可，三层顺序（纯函数→工具薄封装→agent 装配）是否认可。
2. **AC 覆盖矩阵**（§2）：spec 全部 AC 是否确认有承接、无错配（AC-F1/F4/F5 均纳入 P0+ W4 的 T4.1a/T4.1b/T4.1c 是否认可）。
3. **环境/现状处理**（§0.3/0.4）：Python 3.11 依赖钉定 + 旧 v2 清理策略是否认可。
4. **三个 nit**（§0.5：decimal/numpy、time_range、resolver 歧义）是否确认落到 T1.1/T1.4/T2.2。
5. **验收金字塔**（§0.7）：离线 fake 为主 + 真实 smoke（`.env` 真 key）为辅是否认可。
6. 是否允许从 **T0.1** 起 TDD 实现（RED→GREEN→Verify）。

> 负责人验收通过后，按 §3 拓扑从 **T0.1** 开始 TDD 实现；每任务**先红后绿**，Verification 命令产出作为证据。

---

> 本文是 Tasks（原子拆解 + 验收映射）。Implement 阶段强制 TDD；金融确定性模块（metrics/risk/compare）为重点覆盖对象，用 spec §5.B 自洽样例反推。**用框架不造轮子、数字只在 services、两层不变量**贯穿始终。
