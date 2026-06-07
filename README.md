# Stock Deep Research Agent · 股票 Deep Research Agent

面向**非专业用户**的对话式美股研究助手。用户用一句自然语言说"研究哪几家公司、看哪段时间、关注什么"，Agent 自动识别公司、获取行情、确定性计算市场风险、围绕异动检索事件证据、横向比较，最终产出一份**可下载的英文研究报告**。

> 三天面试交付项目。**研究辅助工具，所有输出均声明"不构成投资建议"。**

```text
帮我比较英伟达、阿里巴巴和英特尔最近三个月的表现，分析它们为什么涨跌不同，并重点比较风险。
```

---

## 当前状态

- ✅ **需求已封板**：见 `docs/`（PRD v4，含分层风险规则与全部功能边界）。
- ✅ **工程约束体系就绪**：`.harness/`（风险分级 playbook + 机械化传感器 + 行为 gate）。
- ⏳ **实现尚未开始**：后续严格**按 `.harness/` 流程推进**（PRD → design → implement → review → ship），不直接堆代码。

---

## 三条不可动摇的原则

1. **数字交给代码，理解交给模型** —— 收益率、波动率、最大回撤等所有量化指标由确定性程序计算，大模型不参与原始数值计算，只负责解释表达。
2. **只摆证据与相关性，绝不断言因果** —— 事件只表述"可能相关"，证据不足就说"无法确认"，绝不编造涨跌原因。
3. **来源与时间永远透明** —— 每个数字、结论、事件都带来源、数据时间与新鲜度标注。

---

## 数据源（已实测）

| 能力 | 数据源 |
|---|---|
| 行情（拆股复权日线 + 当前参考价）| **Twelve Data** |
| 新闻 / 事件 / 舆情 | **Tavily** |
| 财报（10-K Item 1A / 外国私人发行人如 BABA 走 20-F Item 3.D）| **SEC EDGAR** |

---

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/stock-deep-research-agent-prd.md`](docs/stock-deep-research-agent-prd.md) | 产品需求基线（PRD v4）：分层风险规则、全部功能边界、三天交付安排 |
| [`docs/stock-research-api-integration.md`](docs/stock-research-api-integration.md) | 数据源接入（Twelve Data / Tavily / SEC，含实测验证） |
| [`docs/interview-presentation-outline.md`](docs/interview-presentation-outline.md) | 面试讲稿框架（产品视角主线 + 预判追问清单） |

---

## 如何推进（harness 流程）

```bash
cat AGENTS.md                       # 顶层地图
cat .harness/README.md              # harness 导航
cat .harness/playbooks/L2-feature.md   # 接到任务先按对应风险层 playbook 走
bash .harness/sensors/check-all.sh  # 任何时候验证当前状态
```

实现层细节（技术栈、模型/runtime、框架、目录结构）将在需求→设计阶段产出独立 **spec** 文档，再进入实现。

---

## 边界与限制

- 覆盖美国上市股票与 ADR；不含 A 股、纯港股、加密、OTC 粉单。
- 单次最多 3 只股票、最长 1 年、每股深挖 ≤ 3 个异动——超出均**明确告知、不静默截断**。
- 风险结论为"观察到的市场价格风险（Observed Market Risk）"，不等于整家公司的综合投资风险。
- 仅供研究参考，**不构成投资建议、买卖推荐或收益承诺**；事件与价格的时间相关性不代表因果。
