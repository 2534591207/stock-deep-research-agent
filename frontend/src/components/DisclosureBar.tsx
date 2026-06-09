// Always-visible data-source and scope disclosure. Persistently present in the
// main layout (it does not scroll away with the conversation) so the user is
// never misled about delay, data provenance, or the research-only boundary.

export default function DisclosureBar() {
  return (
    <div className="border-b border-slate-line/50 bg-ink-800/70 px-4 py-2 text-xs leading-relaxed text-slate-400 sm:px-6">
      <p className="mx-auto max-w-5xl">
        <span className="font-medium text-slate-300">数据来源：Yahoo Finance</span>
        <span className="mx-1.5 text-slate-600">·</span>
        <span>免费、延迟、非实时</span>
        <span className="mx-1.5 text-slate-600">·</span>
        <span>趋势与风险指标基于已完成日线、截至最近交易日</span>
        <span className="mx-1.5 text-slate-600">·</span>
        <span>当前价为延迟参考价，不用于交易</span>
        <span className="mx-1.5 text-slate-600">·</span>
        <span className="text-caution/90">研究参考，非投资建议</span>
      </p>
    </div>
  )
}
