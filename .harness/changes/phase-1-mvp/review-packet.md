# Review Packet — phase-1-mvp（设计评审）

## 评审对象
`backend/plan.md`（设计事实源）+ `backend/spec.md` + `PRD.md` + `frontend/spec.md`（设计索引见 `design.md`）。

## 评审过程
多轮独立评审（外部 Codex 评审 + 独立 architect agent），逐轮提出阻断项并修复：
- 轮 1–2：会话能力（Workspace/Assets/Followup Router/压缩）方向确立。
- 轮 3：provenance / citation / 失效矩阵 / Followup 边界 / 压缩协议硬化。
- 轮 4：不可变 vs 状态分离、行情读 API、202 追问、上传/资产闭环、枚举统一、harness 门禁。

逐项判定与阻断项关闭见 [`../../feedback/runs/phase-1-mvp-design.yaml`](../../feedback/runs/phase-1-mvp-design.yaml)。

## 最终判定
**PASS** —— 独立 architect agent（fresh instance，非作者）+ repo owner sign-off，2026-06-08。5 个阻断项全部关闭。

## 进入 Tasks 的约束
按**纵向业务闭环**分阶段实现：单股闭环 → 多股并行 → 事件研究 → 报告 → 会话/追问 → 上传。避免逐层各写一半。
