# Stock Deep Research Agent

面向**非专业用户**的对话式美股研究助手。用户用一句自然语言说"研究哪几家公司、看哪段时间、关注什么"，Agent 自动识别公司、获取行情、确定性计算市场风险、围绕异动检索事件证据、横向比较，最终产出一份**可下载的英文研究报告**。

> 研究辅助工具，所有输出均声明"不构成投资建议"。

```text
帮我比较英伟达、阿里巴巴和英特尔最近三个月的表现，分析它们为什么涨跌不同，并重点比较风险。
```

---

## 项目状态

当前阶段为**产品需求与设计**：

- ✅ 产品需求与功能边界已定义（见 [`.harness/changes/phase-1-mvp/PRD.md`](.harness/changes/phase-1-mvp/PRD.md)）。
- ✅ 数据源接入已调研并实测（Twelve Data / Tavily / SEC EDGAR）。
- ⏳ 实现进行中（Roadmap）。

> README 描述的是产品目标；并非所有能力都已实现。请以需求基线为准。

---

## 三条核心原则

1. **数字交给代码，理解交给模型** —— 收益率、波动率、最大回撤等量化指标由确定性程序计算，模型不参与原始数值计算，只负责解释表达。
2. **只摆证据与相关性，绝不断言因果** —— 事件只表述"可能相关"，证据不足就说"无法确认"，绝不编造涨跌原因。
3. **来源与时间永远透明** —— 每个数字、结论、事件都带来源、数据时间与新鲜度标注。

---

## 数据源

| 能力 | 数据源 |
|---|---|
| 行情（拆股复权日线 + 当前参考价）| **Twelve Data** |
| 新闻 / 事件 / 舆情 | **Tavily** |
| 财报（10-K Item 1A；外国私人发行人如 BABA 走 20-F Item 3.D）| **SEC EDGAR** |

---

## 项目结构

```
.
├── AGENTS.md                     # 开发/agent 指引 + .harness 说明
├── README.md
├── .harness/                     # AI 工程约束体系（规则/角色/风险分级流程/传感器/变更模板/变更记录）
│   └── changes/phase-1-mvp/      # 第一期变更（SDD：Specify→Plan→Tasks）：PRD.md · backend/(spec.md+plan.md) · frontend/spec.md（暂缓）· api-integration.md · presentation-outline.md
├── requirements.txt · .env.example
└── （实现待建：src/ web/ tests/ app.py）
```

`.harness/` 是本项目的工程约束体系：按风险分级的工作流（playbooks）、角色 prompt（roles）、工程规则（rules）、机械化校验（sensors）、变更模板与变更记录。详见 [`AGENTS.md`](AGENTS.md)。

---

## 文档

- **[`.harness/changes/phase-1-mvp/PRD.md`](.harness/changes/phase-1-mvp/PRD.md)** — 唯一产品需求基线：分层风险规则、功能边界、数据源与接入、实现阶段。
- **[`AGENTS.md`](AGENTS.md)** — 开发 / agent 指引 + `.harness/` 结构说明。

---

## 边界与限制

- 覆盖美国上市股票与 ADR；不含 A 股、纯港股、加密、OTC 粉单。
- 单次最多 3 只股票、最长 1 年、每股深挖 ≤ 3 个异动——超出均**明确告知、不静默截断**。
- 风险结论为"观察到的市场价格风险（Observed Market Risk）"，不等于整家公司的综合投资风险。
- 仅供研究参考，**不构成投资建议、买卖推荐或收益承诺**；事件与价格的时间相关性不代表因果。
