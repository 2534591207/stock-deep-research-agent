// Friendly, retryable error notice. Never renders raw exception text or a
// stack trace — only a calm human message — and the surrounding conversation
// is always preserved by callers.

interface ErrorNoticeProps {
  message: string
  onRetry?: () => void
}

export default function ErrorNotice({ message, onRetry }: ErrorNoticeProps) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-xl border border-caution/40 bg-caution/10 px-4 py-3 text-sm text-slate-200"
    >
      <span aria-hidden className="text-base text-caution">
        ⚠
      </span>
      <span className="flex-1 min-w-[12rem]">{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg border border-slate-line/80 bg-ink-600 px-3 py-1.5 text-xs font-medium text-slate-100 transition hover:border-accent/60 hover:bg-ink-500"
        >
          重试
        </button>
      )}
    </div>
  )
}
