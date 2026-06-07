# Stock Deep Research Agent · 股票 Deep Research Agent

面向**非专业用户**的对话式美股研究助手。用户用一句自然语言说"研究哪几家公司、看哪段时间、关注什么"，Agent 自动识别公司、获取行情、确定性计算市场风险、围绕异动检索事件证据、横向比较，最终产出一份**可下载的英文研究报告**。

> 三天面试交付项目。**研究辅助工具，所有输出均声明"不构成投资建议"。**

```text
帮我比较英伟达、阿里巴巴和英特尔最近三个月的表现，分析它们为什么涨跌不同，并重点比较风险。
```

---

## 三条不可动摇的原则

1. **数字交给代码，理解交给模型** —— 收益率、波动率、最大回撤等所有量化指标由确定性程序计算，大模型不参与原始数值计算，只负责解释表达。
2. **只摆证据与相关性，绝不断言因果** —— 事件只表述"可能相关"，证据不足就说"无法确认"，绝不编造涨跌原因。
3. **来源与时间永远透明** —— 每个数字、结论、事件都带来源、数据时间与新鲜度标注；当前价是"部分市场参考价"还是"已完成收盘价"必须分清。

---

## 功能

- **自然语言理解**：识别 1–3 家公司（中文名/英文名/代码）+ 时间范围（最近一月/三月/半年/今年以来…）+ 关注点。
- **公司识别**：基于支持名单（catalog）+ 别名表裁决，覆盖**美国上市股票与 ADR**（NASDAQ/NYSE，含 BABA 这类中概 ADR）；不在范围如实说明，不编造代码。
- **市场风险（代码计算）**：年化波动率、最大回撤、负收益日波动率、最大单日涨跌；连续风险分数（相对排名）+ 绝对等级（与组合无关、与时间范围相关）。
- **显著波动 + 事件研究**：定位最大单日异动与最大回撤区间 → Tavily 检索时间对得上的事件 → 每个异动给 **Event Attribution Confidence**（High/Medium/Low）。
- **Short-term Market View**：Positive/Neutral/Cautious，收益阈值随时间范围动态缩放；明确声明"非买卖建议"。
- **补充材料**：可上传 PDF/TXT/Markdown 文本作为补充证据，归属到对应公司、标注文件名与页码（不做 OCR / 向量库）。
- **可视化编排**：并行单股研究计划与每步状态实时可见。
- **报告**：多股票英文综合报告，每股 9 节，可下载 Markdown（HTML/PDF 规划中）。
- **稳定降级**：未配置行情 Key 时使用**明确标注的演示数据**，绝不伪装成真实行情。

---

## 架构 / 模块地图

```
app.py                     FastAPI 入口：/（页面）、POST /api/runs、GET /api/runs/{id}
src/
  intent_parser.py         自然语言 → 任务槽位（公司、时间范围、关注点）
  company_resolver.py      公司识别 + 支持名单/别名表 → 规范代码/交易所/标的类型
  market_data.py           Twelve Data 行情接入（报价 + 拆股复权日线）
  market_metrics.py        确定性指标：收益/波动/回撤/显著波动/风险分数与等级
  event_research.py        Tavily 事件检索 + Event Attribution Confidence
  document_analyzer.py     上传文件文本提取（PyMuPDF）+ 归属公司
  reporting.py             英文综合研究报告生成
  orchestrator.py          主 Agent：并行编排单股研究、校验汇总、横向比较
  models.py                Pydantic 数据模型（请求/研究结果统一结构）
web/                       聊天 UI + 研究状态可视化 + 走势图（原生 HTML/CSS/JS）
tests/                     intent_parser / market_metrics / orchestrator 单测
docs/                      产品需求与设计文档（见下）
.harness/                  AI 工程约束体系（风险分级流程 + 机械化传感器 + 行为 gate）
```

数据源：**Twelve Data**（行情，日线默认拆股复权）· **Tavily**（事件/新闻）· **SEC EDGAR**（财报，10-K Item 1A / 外国私人发行人如 BABA 走 20-F Item 3.D）。

---

## 运行

```bash
pip install -r requirements.txt

# Key 均为可选；未配置时行情走标注过的演示数据
export TWELVE_DATA_API_KEY='你的免费 Key'
export TAVILY_API_KEY='你的 Key'
export SEC_USER_AGENT='StockResearchAgent your-email@example.com'

python3 -m uvicorn app:app --reload --port 8000
```

打开 <http://127.0.0.1:8000>。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

---

## 设计文档

| 文档 | 内容 |
|---|---|
| [`docs/stock-deep-research-agent-prd.md`](docs/stock-deep-research-agent-prd.md) | 产品需求基线（PRD v4）：分层风险规则、全部功能边界、三天交付安排 |
| [`docs/stock-research-api-integration.md`](docs/stock-research-api-integration.md) | 数据源接入（Twelve Data / Tavily / SEC，含实测验证） |
| [`docs/interview-presentation-outline.md`](docs/interview-presentation-outline.md) | 面试讲稿框架（产品视角主线 + 预判追问清单） |

---

## 边界与限制

- 覆盖美国上市股票与 ADR；不含 A 股、纯港股、加密、OTC 粉单。
- 单次最多 3 只股票、最长 1 年、每股深挖 ≤ 3 个异动——超出均**明确告知、不静默截断**。
- 当前价为部分市场伪实时参考价；走势分析用已完成日线。未含分红调整时区间收益称 Price Return。
- 风险结论为"观察到的市场价格风险（Observed Market Risk）"，不等于整家公司的综合投资风险。
- 仅供研究参考，**不构成投资建议、买卖推荐或收益承诺**；事件与价格的时间相关性不代表因果。
