// Top bar: product identity plus a button to open the report viewer.

interface AppHeaderProps {
  onOpenReport: () => void
}

export default function AppHeader({ onOpenReport }: AppHeaderProps) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-slate-line/60 bg-ink-800/80 px-4 py-3 backdrop-blur sm:px-6">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-accent-soft text-base font-bold text-white shadow-inner">
          研
        </div>
        <div className="leading-tight">
          <h1 className="text-base font-semibold text-slate-50 sm:text-lg">
            美股研究助手
          </h1>
          <p className="hidden text-xs text-slate-400 sm:block">
            对话式趋势与风险分析 · 按需研究报告
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={onOpenReport}
        className="flex items-center gap-2 rounded-xl border border-slate-line/70 bg-ink-700 px-3.5 py-2 text-sm font-medium text-slate-200 transition hover:border-accent/50 hover:bg-ink-600"
      >
        <span aria-hidden>▤</span>
        <span className="hidden sm:inline">查看报告</span>
        <span className="sm:hidden">报告</span>
      </button>
    </header>
  )
}
