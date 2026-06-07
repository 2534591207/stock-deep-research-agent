# 股票研究 Agent API 接入文档

> 配合产品需求文档 `docs/product-requirements.md`。
> 三个**免费**数据源：行情（Twelve Data）· 新闻事件（Tavily）· 财务事实（SEC EDGAR，可选）。
> 选型原则：全部免费、可复现、不依赖付费实时数据；研究原型阶段，"可信 + 可复现"优先于"全市场实时"。

---

## 1. 结论与选型

| 能力 | 数据源 | 原因 | PRD 分层 |
|---|---|---|---|
| 当前参考价、日线 OHLCV（最长 1 年）| **Twelve Data Basic** | 免费 Key，接口简单，覆盖 NVDA、BABA 等美股 | A 核心 |
| 新闻 / 事件 / 舆情 | **Tavily** | 可按公司 + 日期窗口检索，返回标题、链接、时间、摘要 | 事件能力 |
| 财务事实、最新申报记录 | **SEC EDGAR** | 官方、免费、不需要 API Key | 可选核验 |

> **上传文件**：支持 PDF/TXT/MD **文本提取**作为补充证据（不做 OCR/向量库）；由**本地解析**处理，非外部 API。

### 实时性说明（重要）
不要把免费实时行情用于自动交易。Twelve Data 免费美股实时源覆盖所有美股代码，但**实时成交来自部分市场，约占全市场成交量的 5%**——它给的是该票一个真实、很近的成交参考价，但不保证是"全市场最新一笔"。
- **当前价** → 作为**部分市场伪实时参考价**，报告中明确标注，不用于交易。
- **走势分析** → 一律使用**已完成的日线**（准确，不受部分市场影响）。

---

## 2. 已验证范围

验证日期：2026-06-07。

- **Twelve Data** `price` 与 `time_series` 官方 demo：调用成功，返回 AAPL 当前参考价与日线。
- **SEC** `companyfacts`：成功，返回 NVIDIA 财务事实。
- **SEC** `submissions`：成功，返回 Alibaba 最新申报记录。
- **Tavily** `search`：成功。实测查询 NVIDIA 行情/业绩相关新闻，返回带**标题、链接、摘要**的真实结果，其中包含直接关联股价的报道（例："Nvidia stock slips, Q2 data center revenue disappoints"，来源 Yahoo Finance）——证明"围绕异动找事件证据"这条链路可行。
- 需自有 Key 才能复现的：Twelve Data 的 `NVDA`/`BABA`、Tavily 的全部检索。

任何外部 API 都无法承诺永久 100% 可用。这里通过启动自检、显式错误和降级策略，保证 Agent 在调用失败时**不会编造数据**。

---

## 3. 获取免费 Key 与环境变量

```bash
export TWELVE_DATA_API_KEY='你的-twelve-data-key'   # https://twelvedata.com/pricing 注册 Basic 免费计划
export TAVILY_API_KEY='tvly-你的-key'                # https://app.tavily.com 注册获取
export SEC_USER_AGENT='StockResearchAgent your-email@example.com'  # SEC 要求可联系到开发者的 User-Agent
```

SEC 要求合规 `User-Agent`，请把示例邮箱换成真实邮箱。

---

## 4. 一键验证

行情 + SEC 部分用纯标准库客户端验证，不需安装依赖：

```bash
python3 examples/stock_research_client.py verify
```

未配置 Twelve Data Key 时，它验证 Twelve Data demo 与 SEC；配置 Key 后还会真实验证 NVDA、BABA 的报价与日线。Tavily 检索可另加一条 smoke test（见 §7）。

成功输出结构：

```json
{
  "twelve_data_demo": {"ok": true, "symbol": "AAPL", "price": 307.39001, "bar_count": 5},
  "sec_nvidia_company_facts": {"ok": true, "entity_name": "NVIDIA CORP"},
  "sec_alibaba_recent_filings": {"ok": true, "entity_name": "Alibaba Group Holding Ltd"}
}
```

---

## 5. 行情调用（Twelve Data）

### 当前参考价
```bash
python3 examples/stock_research_client.py quote NVDA
```
```http
GET https://api.twelvedata.com/quote?symbol=NVDA&apikey=${TWELVE_DATA_API_KEY}
```
统一后的关键字段：
```json
{
  "symbol": "NVDA", "exchange": "NASDAQ", "currency": "USD",
  "datetime": "2026-06-05", "price": 205.1, "previous_close": 218.66,
  "percent_change": -6.2, "is_market_open": false,
  "source": "Twelve Data",
  "freshness": "Provider-reported; free US real-time feed is partial-market"
}
```

### 最近一个月走势
```bash
python3 examples/stock_research_client.py history NVDA --outputsize 30
```
```http
GET https://api.twelvedata.com/time_series?symbol=NVDA&interval=1day&outputsize=30&apikey=${TWELVE_DATA_API_KEY}
```
客户端**确定性计算**：区间收益率、区间最高/最低价、日收益率波动率、按日期升序的 OHLCV。
> 这些指标不交给大模型计算（PRD 原则一）。

---

## 6. SEC 财务数据调用（可选核验）

| 公司 | 代码 | CIK |
|---|---|---|
| NVIDIA | NVDA | `0001045810` |
| Alibaba Group ADR | BABA | `0001577552` |

```bash
python3 examples/stock_research_client.py sec-facts 0001045810      # 结构化财务事实
python3 examples/stock_research_client.py sec-filings 0001045810    # 最新申报记录
```
```http
GET https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json
GET https://data.sec.gov/submissions/CIK0001045810.json
User-Agent: StockResearchAgent your-email@example.com
```
NVIDIA 关注 `10-K`/`10-Q`/`8-K`；Alibaba 是外国私人发行人，关注 `20-F`/`6-K`。

---

## 7. 新闻 / 事件检索（Tavily）

围绕代码识别出的"异动日"，限定公司、限定日期窗口检索事件证据。

### 接口
```http
POST https://api.tavily.com/search
Content-Type: application/json
Authorization: Bearer ${TAVILY_API_KEY}
```
```json
{
  "query": "NVIDIA NVDA earnings guidance data center revenue",
  "search_depth": "basic",
  "max_results": 5,
  "start_date": "2026-05-25",
  "end_date": "2026-06-05",
  "include_domains": ["finance.yahoo.com", "reuters.com", "cnbc.com", "nvidianews.nvidia.com"]
}
```
（参数与字段以 [Tavily 官方文档](https://docs.tavily.com/) 为准。亦可通过 Tavily MCP server 调用，参数同名。）

### 返回（关键字段）
每条结果含 `title`、`url`、`content`（摘要）、`published_date`、`score`。报告里每条事件都带 标题 + 时间 + 来源链接。

### 「围绕异动日」检索模式（实测经验）
1. 先用**窄窗**：`start_date`/`end_date` 设为异动日前后各 ~5–7 天。
2. **实测注意**：`start_date`/`end_date` 按 `published_date` 严格过滤，窄窗可能返回为空。若结果太少，**放宽窗口或去掉日期参数重查，再在客户端按 `published_date` 排序、保留最接近异动日的几条**。
3. 每只股票**最多两轮**检索（控制时间与额度）。
4. 用 `include_domains` 优先权威财经源，降噪。

### 归因纪律（强制，PRD 原则二）
- 只呈现"时间对得上的证据 + 谨慎措辞"，**绝不断言因果**：
  > "6 月 3 日 NVDA 下跌 8%，临近有这条报道：[数据中心营收不及预期]（Yahoo Finance，链接）。时间接近，可能是影响因素之一，但不构成因果证明。"
- 找不到像样证据：
  > "当前公开证据不足以确认这一阶段股价变化的主要原因。"

---

## 8. 建议的 MCP Tool 设计

```json
{"name": "get_stock_quote", "description": "获取美股当前参考价格；只用于研究，不用于自动交易",
 "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}}
```
```json
{"name": "get_stock_history", "description": "获取日线并计算确定性走势指标",
 "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"},
   "trading_days": {"type": "integer", "default": 30, "maximum": 260}}, "required": ["symbol"]}}
```
> `maximum: 260` 覆盖 PRD 的最长 1 年（≈252 交易日）；底层 `time_series` 用 `outputsize` 取对应根数。
```json
```
```json
{"name": "get_stock_news",
 "description": "围绕指定公司与日期窗口检索相关新闻与事件证据；用于研究归因，不构成因果证明",
 "inputSchema": {"type": "object", "properties": {
   "company": {"type": "string", "description": "公司名或代码，如 NVIDIA 或 NVDA"},
   "start_date": {"type": "string", "description": "YYYY-MM-DD，异动日前若干天"},
   "end_date": {"type": "string", "description": "YYYY-MM-DD，异动日后若干天"},
   "max_results": {"type": "integer", "default": 5, "maximum": 10}},
  "required": ["company", "start_date", "end_date"]}}
```
```json
{"name": "get_sec_company_facts", "description": "根据 CIK 获取 SEC 官方 XBRL 财务事实（可选核验）",
 "inputSchema": {"type": "object", "properties": {"cik": {"type": "string"}}, "required": ["cik"]}}
```

---

## 9. Agent 分析流程

```text
用户问题（自然语言）
  -> 识别公司与股票代码、解析时间范围
  -> get_stock_quote        （当前参考价，标注"部分市场伪实时"）
  -> get_stock_history      （日线）
  -> 代码确定性计算走势与风险指标
  -> 代码识别显著波动日（异动日）
  -> get_stock_news         （围绕每个异动日检索事件，最多两轮）
  -> LLM 把"时间对得上的证据"与异动并列，谨慎表达可能原因（不断言因果）
  -> 可选 get_sec_company_facts 核验基本面
  -> 生成带来源、时间戳、免责声明的研究报告
```

报告必须包含：行情数据截止时间；当前价是部分市场参考价还是收盘价；事件的时间与来源链接；看多/看空因素与不确定性；"仅供研究，不构成投资建议"。

---

## 10. 错误与降级策略

| 情况 | Agent 行为 |
|---|---|
| Twelve Data 限流或不可用 | 重试两次；失败后用最近缓存，**不得伪造实时价** |
| 当前价不可用 | 只展示最近已完成日线收盘价，并明确标注 |
| Tavily 失败或无结果 | 保留行情分析，标记"事件证据不足"，**不强行解释涨跌** |
| 检索到的新闻与异动时间对不上 | 不纳入；必要时说明无法确认主要原因 |
| SEC 不可用 | 跳过官方核验并标注 |
| 数据来源时间不一致 | 报告分别列出行情截止时间与事件数据时间 |

建议缓存：当前参考价 15–60 秒；日线 收盘后 24 小时；Tavily 同一公司+窗口 6–24 小时；SEC Company Facts 6–24 小时；SEC Submissions 15–60 分钟。

---

## 11. 免费额度与限制

- **Twelve Data Basic**：官方页面显示约每分钟 8 credits、每天 800 credits。三股票 ×（报价+历史）≈ 6 次调用，远在额度内。额度可能调整，投产前查官网。
- **Tavily**：按自有计划额度计费。每次研究控制检索次数（每只股票最多两轮）并缓存窗口结果，避免浪费额度。
- **SEC EDGAR**：免 Key，须提供合规 `User-Agent`，控速并缓存。
- 免费行情/检索适用于个人、内部研究原型。面向外部用户展示或商业再分发前，需重新核对数据授权。

---

## 12. 官方资料

- [Twelve Data Pricing](https://twelvedata.com/pricing)
- [Twelve Data US equities market data](https://support.twelvedata.com/en/articles/9935903-us-equities-market-data)
- [Tavily Docs](https://docs.tavily.com/)
- [SEC EDGAR APIs](https://www.sec.gov/edgar/sec-api-documentation)
