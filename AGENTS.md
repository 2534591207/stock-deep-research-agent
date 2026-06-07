# AGENTS.md

> 本仓库的开发 / agent 指引。**需求基线见 [`.harness/changes/phase-1-mvp/PRD.md`](.harness/changes/phase-1-mvp/PRD.md)**——所有功能、规则、边界以该文件为准。工程执行受 **`.harness/`** 约束体系约束。

## 项目

**Stock Deep Research Agent**：面向非专业用户的对话式美股研究助手。用户用一句自然语言选公司、定时间、提关注点，Agent 自动识别公司、取行情、确定性计算市场风险、围绕异动检索事件证据、横向比较，产出可下载的英文研究报告。研究辅助工具，输出不构成投资建议。

技术栈（计划）：Python + FastAPI + 原生 HTML/CSS/JS；LLM 用 OpenAI。

## 项目结构

```
.
├── AGENTS.md                     # 本指引
├── README.md                     # 项目入口
├── .harness/                     # AI 工程约束体系（见下）
│   └── changes/phase-1-mvp/      # 第一期变更：PRD.md · backend/(spec.md+plan.md) · frontend/spec.md（暂缓）· api-integration.md · presentation-outline.md
├── requirements.txt              # 依赖（计划栈）
└── .env.example                  # 环境变量模板
# 实现按需求基线 + harness 流程产出：src/ web/ tests/ app.py（待建）
```

## `.harness/` 约束体系里有什么

| 路径 | 作用 |
|---|---|
| `README.md` / `HARNESS.md` | harness 导航与说明 |
| `project.yaml` | 项目元数据（栈、语言、源/测试目录） |
| `rules/core/` | 工程规则（core-01..05：显式意图 / given-when-then / 六阶段工作流 / 诚实表达 / 设计-验收） |
| `roles/` | 角色 prompt：`planner` / `analyst` / `implementer` / `reviewer`（评审须独立 agent 执行） |
| `playbooks/` | 风险分级流程：`L0-trivial` … `L3-high-risk`——接到任务先按风险层选 playbook |
| `sensors/` | 机械化校验脚本（`check-all.sh` 等）；任何时候可跑 |
| `changes/phase-1-mvp/` | **第一期需求变更**：`PRD.md`（需求基线）· `backend/`（`spec.md` Specify + `plan.md` Plan，Tasks 待出）· `frontend/spec.md`（暂缓）· `api-integration.md`（数据源接入）· `presentation-outline.md` |
| `changes/_template/` | 变更模板：PRD / design / risk-assessment / review-packet / rollback / acceptance-report |
| `feedback/` | 评审反馈与豁免（waivers） |
| `changelog.md` / `manifest.yaml` | 变更记录与生成清单 |
| `workflow.md` / `gardening.md` | 工作流与维护流程 |

## 三条不可动摇的原则

1. **数字交给代码，理解交给模型**：量化指标由确定性程序计算，模型不参与原始数值计算。
2. **只摆证据与相关性，绝不断言因果**：事件只说"可能相关"，证据不足就说"无法确认"，不编造。
3. **来源与时间永远透明**：每个数字 / 结论 / 事件都带来源、数据时间、新鲜度。

## 关键边界（详见需求基线）

- 覆盖美国上市股票与 ADR；单次 ≤ 3 只、最长 1 年、每股深挖 ≤ 3 个异动；超出均明确告知、不静默截断。
- 风险结论是"观察到的市场价格风险（Observed Market Risk）"，不等于公司综合投资风险。

## 开发约定

1. **以 `.harness/changes/phase-1-mvp/PRD.md` 为唯一需求来源**；新增/改动功能前先对照它。
2. **按 SDD + harness 流程推进**：判风险层（playbook）→ 规范文档 Specify → Plan → Tasks（见下）→ 按任务 TDD 实现 → 评审由独立 agent 执行 → 跑 `bash .harness/sensors/check-all.sh` 验证。
3. 技术栈 / 模型 / 框架等实现细节写在 **Plan（`plan.md`）**，不写进需求基线（PRD）。

## SDD 文档规范（Spec-Driven Development）

每个变更（`.harness/changes/<change>/<component>/`）按规范驱动开发推进，**规范文档是唯一事实源**：

| 阶段 | 文档 | 内容 |
|---|---|---|
| **Constitution** | `.harness/rules/core/` + `PRD.md §2` | 根本大法：工程规则 + 产品原则（不可违背） |
| **Specify** | `spec.md` | 做什么：用户故事 + 验收标准 |
| **Plan** | `plan.md` | 怎么做：架构、API、数据模型、技术选型 |
| **Tasks** | `tasks.md` | 原子任务 + 依赖（**Plan 通过后**产出） |
| **Implement** | 代码 | 按任务 **TDD**：先写失败测试 → 最小实现 → 验证 |

规则：每阶段过了再进下一阶段；评审与实现分开（评审走 `.harness/roles/reviewer.md`，独立 agent）。
