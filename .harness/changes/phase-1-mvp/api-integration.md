# 股票研究 Agent API 接入文档

> 配合产品需求文档 `PRD.md`。
> 三个数据源：行情（**Yahoo Finance / yfinance**，免费无 key）· 新闻事件（**Tavily**，REQUIRED）· 财务事实（**SEC EDGAR**，REQUIRED）。
> 选型原则：全部免费、可复现、不依赖付费实时数据；研究原型阶段，"可信 + 可复现"优先于"全市场实时"。

---

## 1. 结论与选型

| 能力 | 数据源 | 原因 | PRD 分层 |
|---|---|---|---|
| 当前参考价、日线 OHLCV（最长 1 年）| **Yahoo Finance（yfinance）** | 免费、无需 key，含 ADR/BABA；延迟/EOD | 核心（P0） |
| 新闻 / 事件 / 舆情（报告⑤节） | **Tavily** | 可按公司 + 日期窗口检索，返回标题、链接、时间、摘要；`TAVILY_API_KEY` 缺失时该节诚实降级 | **REQUIRED（P0+）** |
| 财务事实、最新申报记录、经营风险（报告⑥⑦节） | **SEC EDGAR** | 官方、免费、不需要 API Key；CIK 动态解析；`SEC_USER_AGENT` 缺失时该节诚实降级 | **REQUIRED（P0+）** |

### 实时性说明（重要）
不要把行情数据用于自动交易。yfinance（Yahoo Finance）提供的当前价约有 **15 分钟延迟**，不保证是全市场最新成交价。
- **当前价** → 作为**延迟参考价**，报告中明确标注「延迟参考价、不用于交易」。
- **走势分析** → 一律使用**已完成的日线**（EOD，准确，不受延迟影响）。

---

## 2. 已验证范围

验证日期：2026-06-07。

- **Yahoo Finance（yfinance）**：`yf.Ticker("NVDA").history(period="3mo")` 调用成功，返回 NVDA 复权日线；`yf.Ticker("BABA")` 同样成功（ADR 覆盖）——免费、无需 key。
- **SEC** `companyfacts`：成功，返回 NVIDIA 财务事实。
- **SEC** `submissions`：成功，返回 Alibaba 最新申报记录。
- **Tavily** `search`：成功。实测查询 NVIDIA 行情/业绩相关新闻，返回带**标题、链接、摘要**的真实结果，其中包含直接关联股价的报道（例："Nvidia stock slips, Q2 data center revenue disappoints"，来源 Yahoo Finance）——证明"围绕异动找事件证据"这条链路可行。
- 需自有 Key 才能复现的：Tavily 的全部检索（需 `TAVILY_API_KEY`）；SEC 需合规 `SEC_USER_AGENT`。

任何外部 API 都无法承诺永久 100% 可用。这里通过启动自检、显式错误和降级策略，保证 Agent 在调用失败时**不会编造数据**。

---

## 3. 获取免费 Key 与环境变量

```bash
# 行情：Yahoo Finance（yfinance）—— 免费、无需 key
export TAVILY_API_KEY='tvly-你的-key'                # https://app.tavily.com 注册获取；缺失时报告⑤节诚实降级
export SEC_USER_AGENT='StockResearchAgent your-email@example.com'  # SEC 要求可联系到开发者的 User-Agent；缺失时报告⑥⑦节诚实降级
```

SEC 要求合规 `User-Agent`，请把示例邮箱换成真实邮箱。`TAVILY_API_KEY` 与 `SEC_USER_AGENT` 缺失不阻止服务启动，但对应报告节会诚实注明不可用。

---

## 4. 一键验证

行情（yfinance）+ SEC 部分用以下命令验证：

```bash
python3 -c "import yfinance as yf; t=yf.Ticker('NVDA'); h=t.history(period='5d'); print('yfinance OK, rows:', len(h))"
python3 examples/stock_research_client.py verify   # 验证 SEC + Tavily
```

yfinance 无需 key，直接运行即可验证行情链路。Tavily 检索需 `TAVILY_API_KEY`（见 §7）。

成功输出结构（SEC 部分）：

```json
{
  "yfinance_nvda": {"ok": true, "symbol": "NVDA", "bar_count": 5},
  "sec_nvidia_company_facts": {"ok": true, "entity_name": "NVIDIA CORP"},
  "sec_alibaba_recent_filings": {"ok": true, "entity_name": "Alibaba Group Holding Ltd"}
}
```

---

## 5. 行情调用（Yahoo Finance / yfinance）

> **无需 API Key**。yfinance 直接调用 Yahoo Finance 公开接口，覆盖全部美股及 ADR（含 BABA）。

### 当前参考价
```python
import yfinance as yf
ticker = yf.Ticker("NVDA")
info = ticker.fast_info
# info.last_price → 延迟参考价（~15 分钟延迟）；标注"延迟参考价、不用于交易"
```

### 日线（复权，最长 1 年）
```python
hist = ticker.history(start="2026-03-01", end="2026-06-01", auto_adjust=True)
# hist 是 DataFrame：Open/High/Low/Close/Volume（auto_adjust=True 即拆股复权）
```

关键字段说明：
```json
{
  "symbol": "NVDA", "exchange": "NASDAQ",
  "source": "Yahoo Finance (yfinance)",
  "freshness": "EOD / delayed; not for trading",
  "calculation_basis": "split_adjusted"
}
```

客户端**确定性计算**：区间收益率、区间最高/最低价、日收益率波动率、按日期升序的 OHLCV。
> 这些指标不交给大模型计算（PRD 原则一）。

---

## 6. SEC 财务数据调用（REQUIRED · 报告⑥⑦节）

> ⚠️ **仅手工核验示例，非实现规范**：下表 NVDA/BABA 的 CIK 只用于人工 smoke 核验。**实现以 plan §5/§7 为准**——CIK 必须由 SEC `company_tickers.json` 的 `ticker→CIK` 映射**动态解析**，**绝不为任何标的硬编码 CIK**（AC-F4）。`SEC_USER_AGENT` 缺失时报告 ⑥⑦ 节诚实降级，不阻塞服务启动。

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

## 7. 新闻 / 事件检索（Tavily · REQUIRED · 报告⑤节）

围绕代码识别出的"异动日"，限定公司、限定日期窗口检索事件证据。

### 接口

> ⚠️ **仅手工核验示例，非实现规范**：下方 `query` 是人工 smoke 用的手写串。**实现以 plan §5/§7 为准**——检索 query 必须由 `{company_name, ticker}` + 通用金融词**模板化生成**，**绝不为单只股票手写专属 query**；窄窗为空须放宽重检索。

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
> `maximum: 260` 覆盖 PRD 的最长 1 年（≈252 交易日）；底层用 yfinance `history(start, end)` 取对应区间日线。
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
{"name": "get_sec_company_facts", "description": "根据 CIK 获取 SEC 官方 XBRL 财务事实（报告⑥节 Financial & Filing Highlights 所需；CIK 由 company_tickers.json 动态解析，不硬编码）",
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
  -> get_sec_company_facts / get_sec_risk_factors（报告⑥⑦节；SEC 不可用时诚实降级）
  -> 生成带来源、时间戳、免责声明的研究报告
```

报告必须包含：行情数据截止时间；当前价是部分市场参考价还是收盘价；事件的时间与来源链接；看多/看空因素与不确定性；"仅供研究，不构成投资建议"。

---

## 9b. 报告走势图图床（GitHub Contents API · 可选 · 报告 Price Trend 节）

> **定位**：这是报告走势图的**托管集成**，与 yfinance / Tavily / SEC 并列为第四个外部集成，但完全可选。缺失或失败时诚实降级，绝不阻塞报告生成。

### 选型与工作方式

| 项 | 说明 |
|---|---|
| **目的** | 将 matplotlib 渲染的走势图 PNG 上传至公开 GitHub 仓库，以 `raw.githubusercontent.com` URL 嵌入报告 Markdown，使下载的 `.md` 在任意在线查看器中均可显示走势图 |
| **接口** | GitHub Contents API `PUT /repos/{owner}/{repo}/contents/{path}`（需 `Authorization: token {GITHUB_TOKEN}`） |
| **公开仓库** | 上传目标必须是**公开仓库**，否则 raw URL 需认证，下载的 Markdown 无法直接显示图片 |
| **URL 格式** | `https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}` |
| **依赖** | `httpx`（已有，无需新增依赖） |

### 配置（三项均可选）

```bash
export GITHUB_TOKEN='ghp_你的token'        # 需要 repo 写权限（Contents: write）
export GITHUB_IMAGE_REPO='owner/repo'      # 目标公开仓库，如 'myname/stock-report-assets'
export GITHUB_IMAGE_BRANCH='report-assets' # 目标分支（默认值；可省略）
```

三项均为可选——不在 `REQUIRED_KEYS` 中，缺失不触发启动 fail-fast。

### 诚实降级（AC-F6）

| 情况 | 行为 |
|---|---|
| 三项配置均已设置且上传成功 | Price Trend 节嵌入 `raw.githubusercontent.com` URL；下载的 Markdown 在任意在线查看器中均可显示走势图 |
| 任一配置项缺失 | `image_host.upload()` 返回 `None`；Price Trend 节退回后端托管 `/reports/{file}.png` 路径；图片在线（通过 Agent 后端）可见，下载后离线不显示 |
| 上传失败（网络错误 / 权限不足等） | 同上（返回 `None`，退回托管路径）；**报告照常生成，不抛错，不阻塞任何其余节** |

> **与其它集成的区别**：yfinance / Tavily / SEC 影响**报告内容数据**；GitHub 图床只影响**走势图是否可在离线 Markdown 中显示**——降级后报告内容（数字、分析结论）完整无损，仅走势图变为在线托管链接。

---

## 10. 错误与降级策略

| 情况 | Agent 行为 |
|---|---|
| yfinance（Yahoo Finance）不可用 | 重试两次；失败后隔离该股、其余继续、对用户说明；**不伪造数据** |
| 当前价不可用 | 只展示最近已完成日线收盘价，并明确标注 |
| Tavily 失败或无结果 | 保留行情分析，报告 ⑤ 节标记"事件证据不足"，**不强行解释涨跌** |
| 检索到的新闻与异动时间对不上 | 不纳入；必要时说明无法确认主要原因 |
| SEC 不可用 | 跳过官方核验并标注 |
| 数据来源时间不一致 | 报告分别列出行情截止时间与事件数据时间 |

建议缓存：当前参考价 15–60 秒；日线 收盘后 24 小时；Tavily 同一公司+窗口 6–24 小时；SEC Company Facts 6–24 小时；SEC Submissions 15–60 分钟。

---

## 11. 免费额度与限制

- **Yahoo Finance（yfinance）**：免费无限额，无需 key；EOD/延迟数据，不承诺实时。
- **Tavily**：按自有计划额度计费。每次研究控制检索次数（每只股票最多两轮）并缓存窗口结果，避免浪费额度。
- **SEC EDGAR**：免 Key，须提供合规 `User-Agent`，控速并缓存。
- 免费行情/检索适用于个人、内部研究原型。面向外部用户展示或商业再分发前，需重新核对数据授权。

---

## 12b. 上传财报文件处理（本地 + 现有 OpenAI key · 无新外部服务）

> **定位**：这是本期新增的第四条处理路径（与 yfinance / Tavily / SEC 并列），但**完全本地**——不调用任何新外部 API，也不引入新的必需 key。

### 文本提取（本地，无外部调用）

| 文件类型 | 提取方式 | 说明 |
|---|---|---|
| **PDF** | **PyMuPDF**（`pymupdf`）本地提取 | 纯本地，无需网络；扫描件 / 无可提取文本 → 诚实报错 422，**不支持 OCR** |
| **TXT / MD** | 直接 UTF-8 读取 | 无需额外依赖 |

### 向量检索（内存计算，复用现有 OpenAI key）

| 步骤 | 实现 | 说明 |
|---|---|---|
| **文本切块** | 滑窗切块（`DOC_CHUNK_CHARS` 字符，`DOC_CHUNK_OVERLAP` 重叠） | 纯本地，无外部调用 |
| **Embeddings** | **OpenAI `text-embedding-3-small`**，通过 `langchain-openai` 的 `OpenAIEmbeddings` | 复用 **`OPENAI_API_KEY`**（无新必需 key）；**不引入向量数据库服务** |
| **相似度检索** | **numpy 余弦相似度，内存计算** | 无需 Chroma / Weaviate / Pinecone 等；文档库存于内存（`session_id → UploadedDoc`） |
| **降级** | embeddings 调用失败 → 退化为关键词检索 | 诚实降级，不伪造，不上抛异常 |

### 诚实降级

| 情况 | 行为 |
|---|---|
| 扫描件 / 无可提取文本 | `POST /upload` 返回 `422`，响应含「不支持 OCR」说明；不伪造提取结果 |
| 文件类型不支持 | `POST /upload` 返回 `415` |
| 文件超过 `MAX_UPLOAD_MB` | `POST /upload` 返回 `413` |
| embeddings API 不可用 | `analyze_document` 工具内退化为关键词检索（诚实降级），不阻塞问答；回答仍基于原文 |
| 文档中无相关内容 | Agent 回答「文档中未提及」，**绝不编造** |
| 未上传文档即问文档 | `analyze_document` 返回 `{status:"no_document"}`；Agent 提示用户先上传 |

### 与其它数据源的区别

| 数据源 | 是否本地 | 是否新增必需 key | 是否引入新外部服务 |
|---|---|---|---|
| Yahoo Finance（yfinance） | 本地库调用 Yahoo 公开接口 | 否 | 否 |
| Tavily | 外部 API | `TAVILY_API_KEY`（可选，缺失诚实降级） | 否 |
| SEC EDGAR | 外部 HTTP | `SEC_USER_AGENT`（可选，缺失诚实降级） | 否 |
| GitHub 图床 | 外部 API | `GITHUB_TOKEN` 等（可选） | 否 |
| **文本提取（PyMuPDF）** | **完全本地** | **否** | **否** |
| **向量检索（OpenAI embeddings + numpy）** | **内存计算，embeddings 调用 OpenAI** | **否（复用 `OPENAI_API_KEY`）** | **否（无向量数据库）** |

> **一句话**：上传文档处理 = 本地提取（PyMuPDF）+ 现有 OpenAI key 做 embeddings + 内存 numpy 检索。**不需要注册任何新服务，不引入新必需 key，不部署任何向量数据库。**

---

## 12. 官方资料

- [yfinance PyPI](https://pypi.org/project/yfinance/) — Yahoo Finance 数据封装，免费无需 key
- [Tavily Docs](https://docs.tavily.com/)
- [SEC EDGAR APIs](https://www.sec.gov/edgar/sec-api-documentation)
- [SEC company_tickers.json](https://www.sec.gov/files/company_tickers.json) — CIK 动态解析来源
