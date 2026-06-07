# Spec — phase-1-mvp / 前端

> 变更：`phase-1-mvp` · 依据：[`../PRD.md`](../PRD.md) §11–§13（可视化编排与报告）
> 状态：**暂缓**——样式未定，先做后端。本文件先锁定**前端的依赖契约与界面范围**，待样式确定后细化为完整前端 spec。

---

## 1. 定位

前端**不接触**数据源或业务逻辑，只**消费后端 API**。后端是稳定契约；前端样式/选型独立演进。

## 2. 与后端的契约（见 [`../backend/spec.md`](../backend/spec.md) §3）

| 用途 | 接口 |
|---|---|
| 新建研究 run | `POST /api/research` |
| 轮询：研究计划 + 每股状态 + 部分/最终结果 | `GET /api/research/{run_id}` |
| 当前会话追问 | `POST /api/research/{run_id}/messages` |
| 上传补充文件 | `POST /api/research/{run_id}/uploads` |
| 下载报告 | `GET /api/research/{run_id}/report?format=markdown` |

前端通过轮询 `GET` 实时呈现编排过程（PRD §11）。

> **后端 v2 新增契约（前端需消费）**：`POST /messages` 返回 `answer`；`GET /results/{id}`、`/comparisons/{id}`、`/assets/{id}` 取完整内容；`GET /reports` + `/reports/{report_id}` 取报告版本；`RunState` 含 `latest_answer`、每股指标摘要、`report_status`、`is_demo_data`。

## 3. 需要呈现的界面（PRD §11）

- 聊天输入 + 文件上传
- 研究计划：阶段一（并行单股）/ 阶段二（横向比较）/ 阶段三（报告）
- 每只股票实时状态：等待 / 执行中 / 已完成 / 部分完成 / 失败
- 已获取证据数、数据缺失 / 降级提示
- 归一化走势对比图
- 最终报告（在线查看）+ 下载；**active 报告版本 + 历史版本列表**
- 追问回答（`answer`）；可**引用报告章节 / 上传文件 / 事件证据**
- **演示数据强标**（`is_demo_data`），不得当实时
- **不展示**：模型思维链、技术日志

## 4. 待定（样式确定后再 spec）

- 视觉 / 布局 / 组件库 / 图表库选型
- 轮询 vs SSE 的前端实现方式
- 报告在线渲染（HTML）的样式

---

> 实现顺序：**后端（`../backend/spec.md`）稳定后**再启动前端；届时本文件细化为完整前端 spec，并补 design / tasks。
