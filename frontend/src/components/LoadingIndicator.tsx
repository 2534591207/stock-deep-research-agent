// Calm, content-agnostic loading indicator (three pulsing dots) plus optional
// label. Used for "agent thinking" in chat and "loading" in the report panel.

interface LoadingIndicatorProps {
  label?: string
}

export default function LoadingIndicator({ label }: LoadingIndicatorProps) {
  return (
    <div className="flex items-center gap-3 text-sm text-slate-400">
      <span className="flex items-center gap-1" aria-hidden>
        <span className="h-2 w-2 rounded-full bg-accent animate-pulse-dot [animation-delay:0ms]" />
        <span className="h-2 w-2 rounded-full bg-accent animate-pulse-dot [animation-delay:160ms]" />
        <span className="h-2 w-2 rounded-full bg-accent animate-pulse-dot [animation-delay:320ms]" />
      </span>
      <span>{label ?? '思考中…'}</span>
    </div>
  )
}
