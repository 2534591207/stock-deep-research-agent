# 设计 — 上传一个财报文件 → 分析 → 基于它对话（RAG-lite · 流式分阶段）

> 新增功能设计。**第一原则：纯增量，绝不改动现有任何逻辑/流程/功能。**
> 现有「对话 + analyze_stocks + generate_report + 报告列表 + 图床 + 流式分阶段进度」全部原封不动；
> 本功能只是**多挂一条分支 + 第三个工具 + 一个上传端点 + 一个内存文档库**，复用现有流式分阶段 UI。
> 设计决策：内存向量检索（RAG-lite，不引入向量数据库服务）+ 分阶段进度展示 + 先总结再回答。

---

## 0. 它推翻了什么（必须同步改 SDD）

现有 PRD §13 / spec §6 明确写「**上传文件本期不做**」「**OCR / 向量库 / 全文 RAG 不做**」。本功能推翻「上传文件不做」与「向量检索不做」两条（**OCR 仍不做**——扫描件诚实报错）。docs 阶段把这两条改成「已支持（单文件 + 内存向量检索）」。

---

## 1. 用户故事 / 目标 UX（DeepResearch 式）

1. 用户在对话框**上传一个财报文件**（PDF / TXT / MD，单个，再传即替换）。
2. 用户发一句 query，例如「帮我分析下这个财报」「它的主要风险是什么」。
3. 前端**复用现有流式分阶段进度**，展示一条 `📄 {文件名} · 文档解读` 轨：
   `读取文件 → 解析内容 → 定位相关内容 → 理解并汇总` 逐阶段亮 + 加载动画。
4. Agent **先简述「这份文件是什么 / 它理解到了什么」**，**再回答用户的具体问题**——全程**基于文档原文、引用出处**，文档没提到就说「文档中未提及」，**绝不编造**。

---

## 2. 红线与不变量（最重要）

- **零回归**：现有 349 个测试必须仍全绿；现有 `/chat`、`/chat/stream`、`analyze_stocks`、`generate_report`、报告/图床/排名/流式 行为**逐字节不变**（无文档上传或非文档问题时，链路与现在完全一致）。
- **纯增量**：新增 `services/document.py`、`POST /upload`、第三个 `@tool analyze_document`、`session_id → 文档`内存库、若干 doc 阶段 id、前端上传 UI + 文档轨。**不改**现有两个工具、现有端点、现有 services 的任何行为。
- **诚实**：答案基于文档原文 + 引用；缺失说「文档未提及」；扫描件/无可提取文本 → 诚实报错（**不做 OCR**）；读财报是**定性解读**，与「价格指标数字全代码算」红线**互不冲突、各管各**。
- **复用**：分阶段进度复用现有 `services/progress.py` 的 `emit_stage` + `/chat/stream` + 前端 `ResearchProgress`，**不另造一套**。

---

## 3. 后端改动（全部增量）

### 3.1 依赖
- 新增 `pymupdf`（PDF 文本提取）。已装、已钉 requirements。
- Embeddings 走**现有** `langchain-openai` 的 `OpenAIEmbeddings`（`text-embedding-3-small`）+ numpy 余弦，**内存计算，不引入向量数据库**。复用现有 `OPENAI_API_KEY`（无新必需 key）。

### 3.2 `services/document.py`（新）
- `extract_text(data: bytes, filename) -> DocText{text, pages, chars}`：PDF 用 PyMuPDF，TXT/MD 直读；**无可提取文本（扫描件）→ raise 诚实错误**。
- `chunk_text(text) -> list[str]`：重叠切块（~`DOC_CHUNK_CHARS` 字符，`DOC_CHUNK_OVERLAP` 重叠）。
- `embed_chunks(chunks, embedder=None) -> np.ndarray`：默认 OpenAIEmbeddings；**`embedder` 可注入**（测试用 fake，离线确定性）。embeddings 不可用 → 退化为关键词检索（诚实降级，不伪造）。
- `retrieve(question, doc, k=DOC_TOP_K, embedder=None) -> list[Excerpt{text, locator}]`：余弦取 top-k（或关键词退化）。
- `summarize(doc, excerpts, llm=None) -> str`：用现有 ChatOpenAI 生成**基于原文**的简短文件概述（`llm` 可注入 fake）。

### 3.3 文档内存库（新，独立于报告库）
- `session_id → UploadedDoc{filename, text, chunks, embeddings, meta}`，**一份/会话**，再传替换。与报告库平行、互不影响。

### 3.4 `POST /upload`（新端点）
- multipart：`file` + 表单字段 `session_id`。
- 流程：校验扩展名（`.pdf/.txt/.md`）+ 大小（`MAX_UPLOAD_MB`）→ `extract_text` → `chunk_text` →（可在此或首个 query 时 embed；为简单可上传即 embed）→ 存库。
- 返回 `200 {filename, pages, chars, status:"ready"}`；错误：`415` 不支持类型 / `413` 过大 / `422` 无可提取文本（扫描件，**不支持 OCR**）。
- **不触碰任何现有端点。**

### 3.5 第三个工具 `analyze_document(question: str)`（新）
- 注册进 `agent.py` 的 `tools=[analyze_stocks, generate_report, analyze_document]`（**现有两个不动**；`parallel_tool_calls=False` 保留）。
- 工具体内**按真实步骤 `emit_stage`**（track 固定 key `__doc__`）：
  `doc_load`(读取文件) → `doc_parse`(解析内容) → `doc_locate`(定位相关内容 = retrieve) → `doc_summarize`(理解并汇总 = summarize + 取相关原文) ，每个 start/done。
- 返回结构化 `{status, summary, excerpts:[{text, locator}]}`；无上传文档 → `{status:"no_document"}`（agent 据此提示用户先上传）。
- **数字红线**：工具只做**文本检索 + 定性概述**，不计算价格指标；若用户在文档场景问的是股票行情，agent 仍走 `analyze_stocks`（互不串）。

### 3.6 `prompts.py`（增补，不删现有规则）
- 新增：当本会话**已上传文档**且用户问及该文档/财报 → 调 `analyze_document`；**先简述这份文件是什么/理解到什么，再回答用户问题**；**严格基于返回的原文 excerpts，引用出处**；文档未提及就说「文档中未提及」，**不编**；未上传却问"这个文件"→ 提示先上传。

### 3.7 `config.py`（新增常量）
- `MAX_UPLOAD_MB=15`、`ALLOWED_UPLOAD_EXTENSIONS=(".pdf",".txt",".md")`、`DOC_CHUNK_CHARS≈1500`、`DOC_CHUNK_OVERLAP≈200`、`DOC_TOP_K=6`、`EMBEDDING_MODEL="text-embedding-3-small"`。**不进 `REQUIRED_KEYS`。**

---

## 4. 前端改动（全部增量）

- **Composer**：加📎附件按钮（可拖拽）→ `POST /upload`（带 `session_id`）→ 显示文件名 chip + 状态（上传中/解析中/就绪/错误）+ 移除。单文件、再传替换。错误诚实提示（类型/过大/扫描件）。
- **流式文档轨**：`/chat/stream` 已有；前端 `STAGE_LABELS` 增 doc 阶段（`doc_load`=读取文件…），`ResearchProgress` 渲染 `__doc__` 轨，标题用已知上传文件名 `📄 {filename} · 文档解读`。**复用现有组件**，非文档轮不受影响。
- 回答仍是普通 markdown（先总结后回答由 prompt 保证），无需特殊渲染。

---

## 5. 流式契约（doc 阶段，叠加在现有协议上）

`/chat/stream` NDJSON 不变，新增 doc 阶段事件：
`{"type":"stage","symbol":"__doc__","stage":"doc_load|doc_parse|doc_locate|doc_summarize","status":"start|done"}`，最终仍 `{"type":"done","reply":...,"reports":...}`（文档轮 `reports` 为 null）。现有 stock 阶段 id 不变。

---

## 6. 测试（离线确定性，注入 fake embedder/llm；零回归）

- `services/document.py`：extract（PDF/TXT 夹具）、chunk、retrieve（fake embedder 确定性）、scanned→raise。
- `/upload`：成功/类型错/过大/扫描件 各分支。
- `analyze_document` 工具：注入 fake doc + fake embedder → 返回 summary+excerpts；无文档→no_document；**断言 doc 阶段事件被 emit**。
- `/chat/stream` 文档轮：fake LLM 调 analyze_document → 流里有 `__doc__` 阶段 + done。
- **回归**：现有 349 全绿 + 前端 `npm run build` 绿。

---

## 7. 实施步骤

1. **后端**：3.1–3.7 全部 + 离线测试（fake embedder/llm）。验收：既有套件 + 新测全绿（offline）。
2. **真实联调验收**：真实上传一份 PDF 财报 → `/chat/stream` 真实 grounded 问答 + doc 阶段流；修复仅真实环境才暴露的问题。
3. **前端**：上传 UI + 文档轨。验收：build 绿 + 浏览器实测。
4. **文档同步**：更新 PRD §13 / spec §6 的「上传/RAG 不做」条目，新增能力/端点/第三工具/依赖/阶段/AC。
5. **终验**：全量回归绿、前端 build 绿、e2e（上传→分阶段→先总结后回答）。

> 停止规则：任一步既有回归不绿 → 立即停下查，绝不带着回归往下走。
