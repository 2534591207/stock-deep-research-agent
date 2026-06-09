# 美股研究助手 · 前端（对话式 Web UI）

一个聚焦的对话式美股研究界面：聊天分析 + 按需研究报告查看器。深色基调、卡片/气泡式布局，
通过 REST 与既有研究后端通信。前端**不做任何金融计算、不生成结论、不画金融图表**——
一切数字、结论、排名、走势图均来自后端；界面只负责展示（含诚实降级原样呈现）。

## 运行

前置：后端在 `:8000` 运行并已启用跨域（CORS）。

```bash
npm install          # 安装依赖（首次）
npm run dev          # 本地开发，默认 http://localhost:5173
npm run build        # 生产构建（类型检查 + 打包）
npm run preview      # 预览构建产物
```

后端地址通过环境变量 `VITE_API_BASE` 配置（见 `.env.example`），默认 `http://localhost:8000`。

## 后端契约（前端依赖的三个端点）

| 用途 | 方法 / 路径 | 说明 |
|---|---|---|
| 对话 | `POST /chat` `{session_id, message}` → `{reply}` | 每次发言调用；`reply` 为 Markdown 文本 |
| 取报告 | `GET /report/{session_id}/latest` → text/markdown | 无报告时返回 404 |
| 健康检查 | `GET /health` → `{ok: true}` | 连通性自检 |

## 结构

```
src/
  App.tsx                 应用根：会话 id Provider + 布局 + 报告面板开关
  components/
    AppHeader.tsx         顶栏 + 打开报告入口
    DisclosureBar.tsx     常驻数据来源/延迟/非投资建议披露条
    ChatPanel.tsx         聊天状态机 + 调 POST /chat
    MessageList.tsx       消息流（自动滚到底 + 加载/错误态）
    MessageBubble.tsx     单条气泡（用户纯文本 / 助手 Markdown）
    Composer.tsx          输入框 + 发送（输入纪律）
    MarkdownView.tsx      唯一受控 Markdown 渲染管线（含图片失败回退）
    ReportPanel.tsx       报告查看器（抽屉）：调 GET /report/{sid}/latest
    ReportView.tsx        报告富文本（复用 MarkdownView）
    EmptyState.tsx        空态（首屏引导 / 无报告）
    LoadingIndicator.tsx  加载指示
    ErrorNotice.tsx       友好错误 + 重试
  lib/
    api.ts                fetch 薄封装 + 错误归一化（404→空态 / 5xx・网络→错误）
    session.ts            客户端会话 id（一标签一份，不持久化）
    SessionContext.ts     只读会话 id Context
    types.ts              共享类型
```

## 设计原则（红线）

- **不算数 / 不编造**：前端无任何金融计算；后端给“未识别 / 证据不足 / 降级”时原样如实展示。
- **披露常驻**：数据来源（Yahoo Finance，延迟、非实时）与“研究参考、非投资建议”持续可见。
- **会话隔离**：每次 `/chat` 携带同一客户端 `session_id`，多轮记忆由后端承载。
- **安全渲染**：Markdown 经受控管线渲染，不裸 `innerHTML` 注入。
