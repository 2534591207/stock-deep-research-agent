# Specify — phase-1-mvp / 后端

> SDD 流程：Constitution → **Specify（本文）** → Plan → Tasks → Implement
> 依据：[`../PRD.md`](../PRD.md)（两层架构定稿版 v6 · 需求基线）· 详细架构与目录见 [`plan.md`](plan.md) · 根本大法 [`../../../constitution.md`](../../../constitution.md)
> 本文是 **WHAT**：用户故事 + 验收标准。**唯一例外**：应负责人要求，在前部写死「技术栈与框架选型」方向（§2），以杜绝造轮子；具体拼装仍归 `plan.md`。

---

## 1. 概述与范围

本产品是一个**对话式美股研究 Agent**，承接 PRD v6 的**两层架构**：**顶层对话 Agent**（闲聊、解释概念、**单股分析**、**横向比较**——全部在对话里直接完成，**这时不出报告**）+ **下层按需报告生成编排**（仅当用户明确要报告时，才启动一条结构化流程，逐只分析 → 汇总 → 横向比较 → 组装每只 9 节的英文报告）。对外只有**两个工具**：`analyze_stocks`（单股分析 + 横向比较，传几只比几只）与 `generate_report`（按需出报告）。**所有数字全由确定性代码算，LLM 只理解 / 路由 / 叙述，绝不算数、不编概率、不断因果**；本产品是**研究辅助，不构成投资建议**。

**范围 = 后端（FastAPI）**：对话端点 + 按需报告端点 + 底层 services（确定性计算）+ providers（真实数据源）。**前端（Vite + React）独立实现，消费同一套 API 契约**（见 [`../frontend/spec.md`](../frontend/spec.md)）。

---

## 2. 技术栈与框架选型（关键 · 用框架不造轮子）

> 本节是**方向性约束**，目的只有一个：除了「金融口径规则」与「薄编排胶水」，**其余一律用成熟库**——不重复造 agent 循环、不手写 session、不手撸 HTTP、不手撸数学循环。详细拼装、目录、版本在 `plan.md`；本节只把「哪里用现成、哪里才自己写」一眼写死。**运行环境 = Python 3.11（venv）。**

### 【用现成框架/库，不要手写】

| 关注点 | 用什么 | 红线（不要做的事） |
|---|---|---|
| 对话 Agent 的工具调用循环 | **LangGraph 现成的 ReAct agent（`create_react_agent`）** | **绝不手写 ReAct 状态机 / 工具调用循环 / 「思考-行动-观察」编排** |
| 会话记忆 | **LangGraph Checkpointer（本期 `MemorySaver`，内存态、`thread_id` 绑定会话）** | **不手写 session 存储 / 历史拼接 / 上下文窗口管理** |
| LLM 接入 + 工具定义 | **LangChain `ChatOpenAI` + `@tool`（结构化输出 `with_structured_output`）** | **不手写 function-calling 协议 / 工具 JSON schema / 返回值 JSON 解析** |
| HTTP 服务 | **FastAPI**（对话端点 / 报告端点 / 健康检查） | **不手写 web 框架 / 路由分发 / 请求体校验** |
| 数据模型 · 配置 · 结构化输出 · 启动 key 校验 | **pydantic + pydantic-settings** | 不手写配置加载 / schema 校验 / 环境变量解析 |
| 行情数据 | **yfinance（Yahoo Finance · 免费 · 无需 key · 含 ADR/BABA · 延迟/EOD）** | **不手撸行情 HTTP 客户端** |
| 公司名模糊匹配（resolver） | **rapidfuzz** | **仅匹配工具**；名单/别名才是"支不支持"的支持边界，rapidfuzz 不做裁决 |
| 指标的底层数值运算（收益序列、标准差、回撤扫描、归一化） | **pandas / numpy 向量化** | **不手撸 Python `for` 循环做数组算术** |
| 走势图 | **matplotlib**（渲染 PNG 嵌入报告） | 不手画坐标系 / 不手拼 SVG |
| 报告排版 | **Jinja2 模板或模板字符串** | 不手写字符串拼接的大段排版逻辑 |
| **新闻事件（报告⑤节，REQUIRED）** | **Tavily SDK** | 不手撸新闻检索 HTTP；`TAVILY_API_KEY` 缺失时该节诚实降级，不阻塞启动 |
| **SEC 申报（报告⑥⑦节，REQUIRED）** | `httpx` + 合规 `SEC_USER_AGENT` | 不手撸正则抓 EDGAR 全文；`SEC_USER_AGENT` 缺失时该节诚实降级，不阻塞启动 |
| **报告走势图图床（可选）** | **GitHub Contents API**（公开仓库 PUT + `raw.githubusercontent.com` URL 嵌入） | `httpx` 已有；`GITHUB_TOKEN` / `GITHUB_IMAGE_REPO` / `GITHUB_IMAGE_BRANCH` 均可选——缺失或上传失败时走势图退回后端托管路径，不阻塞启动，不阻塞报告生成，不伪造数据（AC-F6） |
| **PDF 文本提取** | **PyMuPDF**（`pymupdf`）| 本地提取，无需外部 API；扫描件/无可提取文本 → raise 诚实错误（422）；**不支持 OCR** |
| **文档向量检索** | **OpenAI embeddings（`text-embedding-3-small`）+ numpy 余弦，内存计算** | 复用 `langchain-openai` 的 `OpenAIEmbeddings`；**不引入向量数据库服务**；embeddings 不可用时退化为关键词检索（诚实降级） |

### 【必须我们自己写（但底层运算仍用 numpy / pandas）】

1. **金融口径纯函数（业务核心，必须可单测、可复现）**——这些是产品的护城河，**LLM 不参与**：
   - 区间收益（Price Return / Total Return 标签由复权口径决定）、日波动率、年化波动率、负收益日波动率（MVP 简化口径，如实命名）、最大回撤、最大单日涨跌、Data Coverage、归一化序列（base=100）。
   - `risk_score`（仅用于组内相对排序）、**绝对等级**（Low / Medium / High / Undetermined）、**Short-term Market View**（Positive / Neutral / Cautious / Insufficient data）。
   - 横向比较的**相对排名**（相同区间、相同算法）。
   - 公式与自洽样例见 §5.B；**全部用 §5.B 的自洽样例反推单测**。
2. **薄编排胶水（只是把上面 service 串起来）**：
   - 把上述 service 包成 `@tool` 的**薄封装**（`analyze_stocks` / `generate_report` 工具体）。
   - 报告生成编排的串接（逐只分析 → 汇总 → 比较 → 组装 9 节）——用 **LangGraph 简单顺序流程或普通函数即可**，1–2 只**无需复杂并发**。
   - system prompt + 股票识别别名表 / 全集名单的加载与裁决。

> **一句话原则**：金融口径规则 + 薄编排胶水 = 我们写；agent 循环 / session / HTTP / 数学循环 = 用成熟库。

---

## 3. 用户故事（US）

- **US-1 · 正常对话**：作为一个看得懂涨跌、但没空算指标的研究用户，我想**和 Agent 像聊天一样多轮对话**（包括打招呼、问「你能干嘛」），**这样**我不必学命令或代码就能用它。
- **US-2 · 一句话分析单股**：作为不懂股票代码的用户，我想用大白话说「分析下英伟达最近三个月」，**这样**系统能自己识别公司、取真实行情、用代码算好指标与市场风险，再用人话讲给我听——**不必我懂代码、也不必先出报告**。
- **US-3 · 横向比较看谁更险**：作为想对比的用户，我想把 1–3 只美股放一起说「这几只比比谁风险更高」，**这样**我能在**同一对话里**直接拿到相同口径的相对排名，**而不需要先生成报告**。
- **US-4 · 按需要一份可下载报告**：作为需要存档/分享的用户，我想在**明确说「出一份报告」**时拿到一份**可下载的英文研究报告**（每只 9 节齐全、含免责声明），**这样**我能保存正式产物——**且只有我要的时候才生成**。
- **US-5 · 引用报告继续追问**：作为已拿到报告的用户，我想直接问「报告里阿里第二条经营风险是啥」，**这样**系统能精确定位到那一条复述给我，**不串到别的股票、也不编造**。
- **US-6 · 记得上文、消解指代**：作为多轮对话的用户，我想用「它 / 这三只 / 报告里那条」这种说法，**这样**我不必每轮重复股票名和时间范围，系统记得住。
- **US-7 · 数据/证据不足时被如实告知**：作为怕被误导的用户，当行情取不到、公司识别不了、或某次异动找不到可靠证据时，我想被**如实告知**（给可用范围、标明缺失、不伪造），**这样**我不会基于假结论做判断。
- **US-8 · 上传财报文件并基于它问答**：作为想深入读财报的用户，我想上传一个财报 PDF（或 TXT/MD），**这样**我能直接问「这份文件讲了什么风险」「主要财务亮点是什么」，Agent 先简述文件内容再回答我的具体问题，全程基于文档原文引用、不编造，文档没提到的如实说「文档中未提及」；我还能看到实时的文档解读进度（读取 → 解析 → 定位 → 汇总），复用现有流式分阶段 UI；上传扫描件时系统诚实告知不支持 OCR。

---

## 4. 功能需求（WHAT · 承接 PRD · 简列）

1. **对话 + 每轮意图**：LLM **每轮临场判断**本轮是闲聊 / 解释概念 / 要分析 / 要比较 / 要报告 / 引用报告 / 跑题——**不调工具、调 `analyze_stocks`、还是调 `generate_report` 由它决定**（这是 LLM 工具调用自带的，不单独建一套「意图工程」）。
2. **`analyze_stocks`（单股分析 + 横向比较，不出报告）**：识别公司（中/英/代码 → 锁定美股标的，含 ADR；未命中如实说、不编码）→ 取行情/日线 → **代码算指标**（§5.B）→ **代码定市场风险等级**（Low/Med/High/Undetermined + Short-term Market View）→ 传入多只时用**相同口径**做横向比较与相对排名。**传 1 只就是单股分析，传 2–3 只就附比较；全程不出报告。**
3. **`generate_report`（按需编排出报告）**：仅当用户明确要报告时触发 → 启动结构化编排（逐只固定分析 → 汇总 → 横向比较 → 组装每只 **9 节** 英文 Markdown）→ 含归一化走势（base=100）、市场风险、相关事件（⑤ Related Events）、财务与申报亮点（⑥）、经营风险（⑦ Business Risks）、Short-term Market View、证据与限制、**英文逐字免责声明**；⑤⑥⑦ 数据源不可用时各节诚实降级注明，不阻塞报告生成；**可下载**；**报告进会话记忆，可被引用**。
4. **引用报告定位**：用户引用报告某只某节某条（「阿里第二条风险」）→ 走**报告章节索引 / 会话记忆**精确定位，**不靠 LLM 猜**。
5. **会话记忆 + 指代消解**：单会话内存态（Checkpointer）；记住当前股票/时间/关注点/已有结论/当前报告；消解「它/这三只/报告里那条」。
6. **边界 / 降级 / fail-fast**：边界对用户始终可见、永不静默截断（§5.H）；运行期某源失败诚实降级、不伪造（§5.F）；启动缺所需 key 即 fail-fast（§5.G）。
7. **诚实贯穿**：数字代码算、不断因果、来源/数据时间/新鲜度透明、当前价标「延迟参考价、不用于交易」、不构成投资建议。

---

## 5. 验收标准（AC · Given-When-Then · 精确可测、逻辑自洽）

> 约定：本节 AC 以**后端行为**衡量（对话工具调用 / API 响应 / 纯函数返回值），**不依赖固定股票、固定句式、固定流程**。**贯穿不变量**（每条 AC 都不得违背）：①**分析在对话里、报告按需**——`analyze_stocks` 永不产出报告，`generate_report` 仅被明确要求时触发；②**数字全代码算**——所有量化断言针对 services 纯函数，LLM 不参与；③**两个工具**，无第三个。

### A. 对话能力（顶层 · 不调工具也能用好）

- **AC-A1（覆盖 PRD V1 / 能力「闲聊」）** _Given_ 用户说「你好，你能干嘛？」 _When_ Agent 处理本轮 _Then_ **不调用任何工具**（断言：本轮 tool-call 列表为空）、**不产出报告**，回复为自然语言的能力自我介绍，并**包含「研究参考 / 非投资建议」性质提示**。
- **AC-A2（覆盖 PRD 能力「解释金融概念」）** _Given_ 用户问「什么是波动率？」（或回撤 / ADR）_When_ Agent 处理本轮 _Then_ **不调用任何工具**，直接用自然语言解释概念（断言：tool-call 列表为空）。
- **AC-A3（覆盖 PRD §12 跑题 / 非美股）** _Given_ 用户输入与美股研究无关的话题，或要求分析仅港股/A股/加密/OTC 标的 _When_ Agent 处理本轮 _Then_ **礼貌拒答并说明产品范围**（只覆盖美国上市股票及 ADR），**不调工具、不编造标的**。

### B. 单股分析（确定性 · 重点 TDD · 数字全代码算）

> 口径锁定（与 PRD §8 / plan §6 一致，单测据此写）：
> - 日收益 `daily_return[t] = adjusted_close[t] / adjusted_close[t-1] − 1`。
> - 日波动率 = **样本标准差**（`ddof=1`）of 日收益；年化波动率 = 日波动率 × **√252**。
> - 负收益日波动率 = 仅取负收益日的样本标准差 × √252；**负收益日 < 2 → N/A**（返回 null + reason，不是字符串 "N/A"）。
> - 最大回撤 = 区间内**最高 adjusted_close** → 其后**最低 adjusted_close** 的最大跌幅（signed，≤0）。
> - 最大单日 = 日收益中 **|值| 最大**者，**保留符号**；**|幅度| < 2% → 记「无显著异动」**。
> - Data Coverage = **有效日线 / 预期交易日**（按市场日历）。
> - 风险打分：`vol_score = min(日波动率/0.05, 1)×100`；`drawdown_score = min(|最大回撤|/0.30, 1)×100`；`risk_score = vol_score×0.6 + drawdown_score×0.4`（**仅用于组内相对排序**）。
> - 绝对等级（**最严重优先**，含边界）：有效日线 < 10 或 Coverage < 0.8 → **Undetermined**；**日波动率 ≥ 0.03 或 最大回撤 ≤ −0.20 → High**；**日波动率 ≥ 0.015 或 最大回撤 ≤ −0.10 → Medium**；否则 **Low**。
> - `return_threshold = 0.05 × √(预期交易日 / 21)`。**必须用「预期交易日」(按市场日历)、不可用「有效日线」**——否则少给数据会反而更易判 Positive/Cautious（与 plan §6.4 / tasks T1.2 防御点一致）。
> - Short-term Market View：缺数 / 有效日线 < 10 / Coverage < 0.8 → **Insufficient data**；等级 High → **Cautious**；区间收益 < −阈值 → **Cautious**；区间收益 > +阈值 → **Positive**；否则 **Neutral**。

- **AC-B1（覆盖 PRD V2 指标 / 能力「单股分析」）** _Given_ 一份**固定日线夹具** _When_ 调用 `analyze_stocks`（传 1 只）_Then_ 返回的 **区间收益 / 日波动率 / 年化波动率 / 最大回撤 / 最大单日 / Data Coverage 与按上述口径手算一致**（逐项数值断言，内部 decimal，容差仅取浮点末位）。**强调：这些数全由代码算，LLM 不参与。**
- **AC-B2（负收益日边界）** _Given_ 夹具中负收益日数量 < 2 _When_ 计算负收益日波动率 _Then_ 返回 **null + reason**（如 `insufficient_negative_days`），**不是字符串 "N/A"**，且不影响其它指标。
- **AC-B3（最大单日「无显著异动」边界）** _Given_ 夹具中所有日收益 |幅度| < 2% _When_ 计算最大单日 _Then_ 标记「无显著异动」（`significant=false`），**不强行找事件**。
- **AC-B4（风险分层自洽样例反推 · 核心 TDD · 与 PRD NVDA 脚本同一套数）** _Given_ 一只股票算得 **日波动率 = 0.02665、最大回撤 = −0.138、区间收益 = −0.104、预期交易日 = 63** _When_ 代码计算风险 _Then_ **逐项精确断言**：`vol_score = 53.3`、`drawdown_score = 46.0`、**`risk_score ≈ 50.4`（精确 50.38 = 53.3×0.6 + 46.0×0.4，单测可断言 50.38 或 ±0.1 容差）**、**`absolute_level = Medium`**、`return_threshold = 0.0866`（= 0.05×√(63/21)）、**`short_term_market_view = Cautious`**（因 −0.104 < −0.0866）。（此样例与 **PRD v6 NVDA 对话脚本一致**：年化波动率 ≈ 42.3%（= 0.02665×√252）、最大回撤 −13.8%、Medium、Cautious——全项目共用这一个自洽样例。）
- **AC-B5（等级阈值边界 · High/Medium 切换）** _Given_ 参数化夹具：(日波动率=0.030, 回撤=0) → **High**；(0.015, 0) → **Medium**；(0.0149, 回撤=−0.10) → **Medium**（回撤触发）；(0.0149, −0.099) → **Low** _When_ 计算绝对等级 _Then_ 与上述一致（**断言阈值含边界：≥0.03 / ≤−0.20 取 High；≥0.015 / ≤−0.10 取 Medium；最严重优先**）。
- **AC-B6（数据不足 → Undetermined，不参与排名）** _Given_ 某股**有效日线 < 10** 或 **Data Coverage < 0.8** _When_ 计算风险与市场观点 _Then_ `absolute_level = Undetermined`、`short_term_market_view = Insufficient data`，且该股**被排除出横向比较的相对排名**（呼应 AC-C4）。

### C. 横向比较（在对话里 · 不出报告）

- **AC-C1（覆盖 PRD V3 / 能力「横向比较」）** _Given_ 用户在对话里要求把 2–3 只美股一起比 _When_ `analyze_stocks`（传 2–3 只）_Then_ 用**相同区间、相同算法**算各只指标并给**相对排名**（按 `risk_score` 排序），返回排名结果。
- **AC-C2（risk_score 相同 → 并列）** _Given_ 两只股票 `risk_score` 相等 _When_ 计算相对排名 _Then_ 二者**并列同名次**（断言相同 rank 值）。
- **AC-C3（单只不排名）** _Given_ 只传 1 只 _When_ `analyze_stocks` _Then_ **不产出相对排名**（单股分析无比较语义）。
- **AC-C4（Undetermined 排除）** _Given_ 多只中某只为 Undetermined（见 AC-B6）_When_ 排名 _Then_ 该只**不进入相对排名**，排名 caveat 说明其被排除。
- **AC-C5（结论带范围 caveat）** _Given_ 任意一次横向比较 _When_ 返回结论 _Then_ **必须带「仅限本次所选股票与区间」caveat**（断言结论文本/字段含该限定，不宣称代表全市场或更长周期）。
- **AC-C6（比较全程不出报告 · 不变量）** _Given_ 上述任一比较场景 _When_ Agent 完成本轮 _Then_ **断言本轮未触发 `generate_report`**（比较走「分析」分叉，不经报告编排）。

### D. 报告编排（按需 · 仅被明确要求时触发）

- **AC-D1（覆盖 PRD V4 / 能力「按需出报告」）** _Given_ 已在对话里分析/比较过 1–N 只，用户明说「出一份报告」 _When_ Agent 处理本轮 _Then_ **此刻才触发** `generate_report`（断言本轮 tool-call 含 `generate_report`），系统为**每只股票分别产出一份独立的英文 Markdown 报告**（2 只时产出 2 份独立文档，不合并为一份），**每份 9 节齐全**（列出节标题：① Company Snapshot ② Price Trend ③ Observed Market Risk ④ Significant Move ⑤ Related Events ⑥ Financial & Filing Highlights ⑦ Business Risks ⑧ Short-term Market View ⑨ Evidence & Limitations），**Price Trend 节含归一化序列（base=100）**，**每份报告单独可下载**；响应包含报告列表（每项含 `report_id`、`title`、`symbol`、`download_ref`），用户从列表中选择查看某只报告。（注：2 只的报告请求产出 2 份独立文档，各自的 §3 节可含该批次相对排名行 + caveat。）
- **AC-D2（免责声明逐字 · 不得意译或缩写）** _Given_ 报告已生成 _When_ 读取报告正文 _Then_ 含与 PRD §9 **逐字一致**的英文免责声明，字符串比对断言以此为基准：
  > `This report is generated from market data and public information within the specified period, for information aggregation and research reference only. It does not constitute investment advice, a buy/sell recommendation, or any return guarantee. Temporal correlation between events and price changes does not prove causation. Market prices can change rapidly; please make independent decisions based on your own risk tolerance and after consulting a professional.`
- **AC-D3（没要报告 → 不产出报告 · 不变量）** _Given_ 用户只做了分析或比较、**没有**明确要报告 _When_ Agent 完成这些轮次 _Then_ **断言全程未触发 `generate_report`、不存在报告产物**（呼应 PRD「脚本 b、c 不出报告，直到脚本 d」）。
- **AC-D4（流式报告进度 · `POST /chat/stream`）** _Given_ 客户端向 `POST /chat/stream` 发起一次触发 `generate_report` 的请求 _When_ 后端执行报告编排 _Then_ 响应 Content-Type 为 `application/x-ndjson`，流中按规范顺序包含每只股票的十个阶段进度事件（各阶段各一次 `start` 、一次 `done`，`symbol` 为对应 ticker；`compare` 阶段 `symbol="__batch__"`），最后一行为 `{"type":"done","reply":<str>,"reports":[...]}`；**流中不出现未定义的 stage id**，stage id 严格取自规范集合（`identify` / `market_data` / `metrics` / `risk` / `compare` / `chart` / `events` / `filings` / `risk_factors` / `assemble`）。_Given_ 本轮不触发 `generate_report`（闲聊或分析轮次）_When_ 流结束 _Then_ 流中**无任何阶段进度事件**，仅一行 `{"type":"done","reply":<str>,"reports":null}`。（注：`POST /chat` 同步端点行为不变，不受本 AC 影响。）

### E. 引用报告（精确定位 · 不串台 · 不编造）

- **AC-E1（覆盖 PRD V5 / 能力「引用报告追问」）** _Given_ 报告已生成且含多只股票各自的 Business Risks _When_ 用户问「报告里阿里第二条经营风险是啥？」 _Then_ 经**报告章节索引 / 会话记忆**精确定位到 **BABA 的 Business Risks 第 2 条**（断言定位到的 owner = BABA、section = Business Risks、item = 2），复述该条要点 + 来源；**绝不误用其它股票的风险、绝不编造**（走索引，不靠 LLM 猜）。

### F. 诚实与降级（运行期 · 不伪造）

- **AC-F1（Related Events 诚实降级 · 必须适用）** _Given_ 某次显著异动**找不到可靠新闻证据**（Tavily 返回空、key 缺失、或 API 不可用）_When_ 报告 ⑤ Related Events 节生成 _Then_ **该节如实注明「未找到可靠证据 / 事件检索不可用」，`attribution_confidence` 标 Low，不编造原因**；该股的**行情指标分析与报告其余节照常给出**（事件缺失不阻塞核心分析）。每条事件条目（有则）必须含：`title` + `url` + `source` + `date`；`explanation` 仅描述相关性、不断因果；`attribution_confidence` 保守默认 Low，只有强直接证据才升 Medium/High。
- **AC-F2（单股行情失败隔离）** _Given_ 多股请求中某一只**行情取数失败** _When_ `analyze_stocks` 处理该批 _Then_ **隔离该股（标 failed/缺失）、其余股票照常完成**，并**对用户说明哪只失败**；不因一只失败而整批中断、不伪造其数据。
- **AC-F3（当前价标注）** _Given_ 任意分析涉及当前价 _When_ 展示当前价 _Then_ **标注「延迟参考价、不用于交易」**（断言含该标注），与已完成日线的口径区分清楚。
- **AC-F4（Financial & Filing Highlights 必要字段与诚实降级）** _Given_ 报告 ⑥ Financial & Filing Highlights 节生成 _When_ SEC EDGAR 可用且标的有对应 filer _Then_ 该节列出近期申报记录（每条含 `form`、`date`、SEC 链接）；关键财务数据来自 SEC XBRL `companyfacts` API 并附 source 链接；**CIK 必须由 `company_tickers.json` 的 `ticker→CIK` 映射动态解析，绝不硬编码任何标的的 CIK**（断言：代码中不出现写死的 CIK 字符串）。_Given_ `SEC_USER_AGENT` 缺失或 SEC 不可用 _When_ 生成该节 _Then_ **该节诚实注明不可用，不阻塞报告其余节**。
- **AC-F5（Business Risks 必要字段与诚实降级）** _Given_ 报告 ⑦ Business Risks 节生成，标的有最新 10-K（或 20-F for ADR） _When_ 提取 Item 1A 风险因素 _Then_ 每条风险条目含**逐字提取的风险标题**（`title`，原文，非 LLM 改写）+ SEC 来源链接（`source_url`）；**绝不编造或改写风险标题**（断言：title 字符串与真实文件内容一致）。_Given_ SEC 不可用或提取失败 _When_ 生成该节 _Then_ **该节诚实注明提取失败，不阻塞报告其余节**。
- **AC-F6（报告走势图图床诚实降级）** _Given_ 报告 ② Price Trend 节生成时，GitHub 图床配置缺失（`GITHUB_TOKEN` / `GITHUB_IMAGE_REPO` / `GITHUB_IMAGE_BRANCH` 任一未设置）或图床上传失败 _When_ 渲染走势图 _Then_ 走势图嵌入路径**退回到后端托管的 `/reports/{file}.png` 路径**（图片在线可见，下载后离线不显示），**报告照常生成**，**不抛出错误、不阻塞任何其余节**；报告正文或 Evidence & Limitations 节**诚实注明**图片为本地托管路径（下载后离线查看可能不显示图片）。_Given_ 三项 GitHub 配置均已设置且上传成功 _When_ 渲染走势图 _Then_ Price Trend 节嵌入 `raw.githubusercontent.com` 的公开 URL，下载的 Markdown 在任意在线查看器中均可显示走势图。（注：`GITHUB_TOKEN` 等三项不在 `REQUIRED_KEYS` 中，缺失不触发启动 fail-fast。）

### G. fail-fast（启动期 · 只列 key 名 · 绝不 demo/mock）

- **AC-G1（缺核心 key → 启动即报错，只列名）** _Given_ 服务进程启动时，**核心所需 key 缺失或为空字符串**（核心：**仅 `OPENAI_API_KEY`**——行情用 Yahoo Finance 免费无 key；`TAVILY_API_KEY` 与 `SEC_USER_AGENT` 缺失时对应报告节（⑤⑥⑦）运行时诚实降级，**不触发启动失败**）_When_ 启动校验执行（在第一个请求到达之前）_Then_ **进程拒绝启动**，抛出包含**所有缺失核心 key 名称**的错误；**错误消息只含 key 的名称、绝不打印其值**（断言：每个缺失 key 名可被独立字符串命中，且不出现任何疑似真值）。可通过清空不同 key 子集（单个/多个/全部）分别断言。
- **AC-G2（绝不 demo/mock 兜底）** _Given_ 缺 key 这一配置错误 _When_ 系统启动 _Then_ **唯一合法行为是拒绝启动**——**不得提供任何 demo 数据 / mock 响应 / 降级伪造数据**作为兜底（诚实报错优于假数据）。

### H. 边界与通用性（不依赖固定样本 · 永不静默截断）

- **AC-H1（覆盖 PRD V2 通用性）** _Given_ 用户问任意非固定样本的支持标的（如 MSFT / AMZN / COST 等）_When_ `analyze_stocks` _Then_ 经名单/别名表识别并走**完整分析流程**，**不依赖固定股票代码或固定句式**（断言：流程对这些标的同样成立）。
- **AC-H2（覆盖 PRD §12 超过上限）** _Given_ 用户一次请求 > 3 只 _When_ `analyze_stocks` _Then_ **告知上限、默认取前 3 只、其余明确标注被推迟**，把控制权交还用户（不静默丢）。
- **AC-H3（覆盖 PRD §12 未给时间）** _Given_ 用户未指定时间范围 _When_ 解析时间 _Then_ **默认最近 30 天并明确告知**。
- **AC-H4（覆盖 PRD §12 歧义）** _Given_ 公司表达多匹配或没给公司 _When_ Agent 处理 _Then_ **只问一个澄清问题**（不堆叠多问、不擅自假设）。
- **AC-H5（覆盖 PRD V7 / 能力「识别 ADR」）** _Given_ 用户说「阿里巴巴」 _When_ 公司识别 _Then_ 识别为 **BABA · NYSE · ADR**（美股 ADR），**绝不混淆为港股 9988.HK**；识别后向用户展示实际标的。
- **AC-H6（覆盖 PRD V6 / §12 识别失败）** _Given_ 用户要求分析一个**不存在或非美股上市**的标的 _When_ 公司识别 _Then_ **如实说「未找到对应美股上市标的」、给可用范围、绝不编造代码**。

### I. 上传文件与文档问答（US-8 · 增量功能，零回归）

> **贯穿不变量**：文档功能纯增量——现有 `/chat`、`/chat/stream`、`analyze_stocks`、`generate_report`、报告/图床/流式进度行为**逐字节不变**；无文档上传或非文档问题时，链路与现在完全一致。

- **AC-I1（上传成功 · 元数据返回）** _Given_ 客户端向 `POST /upload` 提交合法文件（PDF/TXT/MD，大小 ≤ `MAX_UPLOAD_MB`，含可提取文本）及 `session_id` _When_ 后端处理 _Then_ 返回 `200 {filename, pages, chars, status:"ready"}`；文件被解析为文本块并存入该会话的内存文档库（再次上传则替换）；**不触碰任何现有端点**。
- **AC-I2（上传错误 · 诚实报错 · 不做 OCR）** _Given_ 客户端提交以下情况之一：(a) 不支持的扩展名（非 `.pdf/.txt/.md`）；(b) 文件大小超过 `MAX_UPLOAD_MB`；(c) PDF 无可提取文本（扫描件） _When_ 后端处理 _Then_ 分别返回 `415`（不支持类型）/ `413`（过大）/ `422`（无可提取文本，**不支持 OCR**，不伪造提取结果）；错误响应含人可读的说明文字；**不做任何 OCR 尝试**。
- **AC-I3（文档问答 · `analyze_document` · 流式分阶段 · 先总结再回答 · 严格基于原文）** _Given_ 会话已有上传文档，用户问及该文档相关问题 _When_ Agent 处理本轮 _Then_：(a) 调用 `analyze_document(question)`；(b) 工具体按顺序 emit 四个阶段各一次 `start`/`done`（`symbol="__doc__"`，`stage` 依次为 `doc_load` / `doc_parse` / `doc_locate` / `doc_summarize`），事件通过 `/chat/stream` NDJSON 推送到前端，复用现有流式协议；(c) 最终回答**先简述「这份文件是什么 / 理解到了什么」，再回答用户具体问题**；(d) 回答**严格基于 `analyze_document` 返回的 excerpts 原文，引用定位信息**；(e) 文档中不存在的内容回答「文档中未提及」，**绝不编造**；(f) `/chat/stream` 最后一行仍为 `{"type":"done","reply":<str>,"reports":null}`（文档轮次 `reports` 为 null）。
- **AC-I4（无文档或非文档问题 · 现有流程不受影响）** _Given_ (a) 会话**无**已上传文档，用户问「这个文件…」；或 (b) 会话有文档但用户问的是股票行情/报告（非文档问题） _When_ Agent 处理 _Then_：情况 (a) → Agent 提示用户先上传文件，**不调 `analyze_document`**，不调其他工具；情况 (b) → 正常走 `analyze_stocks` / `generate_report` 对应分叉，**`analyze_document` 不被调用**；两种情况下**现有股票分析与报告流程完全不受影响**（断言：非文档轮次流中无 `__doc__` stage 事件）。

> **A–H + I 对 PRD §14 验收场景全覆盖核对**：V1→AC-A1；V2→AC-B1 / AC-H1；V3→AC-C1 / AC-C5；V4→AC-D1 / AC-D3；V5→AC-E1；V6→AC-H6 / AC-F2；V7→AC-H5；**脚本 f（文档上传+问答）→ AC-I1 / AC-I2 / AC-I3 / AC-I4**。**两层不变量**（分析在对话里不出报告 / 报告按需编排）由 AC-C6、AC-D1、AC-D3 共同钉死。**⑤⑥⑦ 节必做**：AC-F1（Related Events 诚实降级）、AC-F4（Financial & Filing Highlights + 动态 CIK）、AC-F5（Business Risks 逐字提取）。**图床诚实降级**：AC-F6（GitHub 图床不可用 → 退回后端托管路径，报告照常生成）。**流式报告进度**：AC-D4（`POST /chat/stream` NDJSON 流 + 十个规范 stage id + 非报告轮次仅 done 事件）。**文档上传与问答**：AC-I1..I4（`POST /upload` + `analyze_document` + `__doc__` 流式阶段 + 零回归不变量）。

---

## 6. 非目标（本期明确不做）

- 账号系统 / 登录 / 跨会话历史 / 刷新或重启后的状态恢复。
- 交易执行 / 买卖建议 / 目标价 / 估值（DCF 等）/ 仓位建议 / bull-bear 辩论。
- **OCR**：扫描件 / 无可提取文本 → 诚实报错 422，**不支持光学字符识别**（此条保留）。
- **向量数据库服务**：文档检索用内存 RAG-lite（OpenAI embeddings + numpy 余弦），**不引入独立向量库服务**（Chroma / Weaviate / Pinecone 等）。
- **跨文档全文 RAG**：仅支持用户本次会话上传的单个财报文件，不是全库多文档检索。
- 多市场（A 股 / 港股 / 加密 / OTC 粉单）。
- 多用户。
- **PDF 报告导出**：本期只交 **Markdown**（PDF 后续阶段）。
- **已砍掉的旧 ceremony（不再是产品中心，降为实现细节或直接移除）**：失效矩阵作为对外卖点、报告显式版本化协议作为产品承诺、202/409 并发语义作为用户可见行为、独立的「压缩协议」、把每个意图写死成「13 项意图工程」、以及**「强制每轮出报告」的固定流水线**。

---

> 本文只到 **WHAT（用户故事 + 验收标准）+ 选型方向**。详细架构、目录、API 契约、数值实现细节见 [`plan.md`](plan.md)；Implement 阶段强制 TDD（每个 AC 有对应测试，§5.B 确定性 AC 用自洽样例反推）。
