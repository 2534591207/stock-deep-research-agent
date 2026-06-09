// Calm empty states for two contexts: the first-load chat screen (a short
// welcome plus example prompts) and the report panel before any report exists.
// Example prompts are illustrative starting points only — the frontend never
// fabricates analysis or numbers.

interface EmptyStateProps {
  variant: 'chat' | 'report'
  onPickExample?: (text: string) => void
}

const CHAT_EXAMPLES: string[] = [
  '分析下英伟达最近三个月的趋势和风险',
  '英伟达和苹果比比谁波动更大，谁风险更高？',
  '英伟达最近有什么利好新闻吗？',
  '帮我生成一份英伟达的研究报告',
  '上传一份财报（点左下角 📎），让我帮你解读经营风险',
]

export default function EmptyState({ variant, onPickExample }: EmptyStateProps) {
  if (variant === 'report') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-slate-line/70 bg-ink-700 text-xl text-slate-500">
          ▤
        </div>
        <p className="text-sm font-medium text-slate-200">本会话还没有报告</p>
        <p className="max-w-xs text-sm leading-relaxed text-slate-400">
          先在对话里请求一份，例如“生成一份英伟达的研究报告”，生成后即可在此查看。
        </p>
      </div>
    )
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-5 px-4 py-10 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-line/70 bg-ink-700 text-2xl text-accent">
        ◑
      </div>
      <div className="space-y-1.5">
        <h2 className="text-lg font-semibold text-slate-100">
          开始一次美股研究对话
        </h2>
        <p className="text-sm leading-relaxed text-slate-400">
          用大白话提问即可。趋势与风险指标全部由后端基于已完成日线确定性计算，
          助手只负责理解与讲解，不替你做投资决策。
        </p>
      </div>
      <div className="flex w-full flex-col gap-2">
        {CHAT_EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => onPickExample?.(ex)}
            className="group rounded-xl border border-slate-line/70 bg-ink-700/60 px-4 py-3 text-left text-sm text-slate-300 transition hover:border-accent/50 hover:bg-ink-600"
          >
            <span className="mr-2 text-accent/70 group-hover:text-accent">→</span>
            {ex}
          </button>
        ))}
      </div>
    </div>
  )
}
