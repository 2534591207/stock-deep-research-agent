// Live per-stock stage-progress cards rendered while a Deep Research stream is
// in flight. Each stock gets its own card; "__batch__" (the cross-stock compare
// stage) is shown as a slim inter-card row to keep the visual flow linear.
// "__doc__" is the document-analysis track — rendered as a distinct card with
// a 📄 prefix and doc-specific stages (doc_load…doc_summarize).

import { STAGE_LABELS, STAGE_ORDER, type ResearchProgressState, type StageEntry, type UploadedDoc } from '../lib/types'

// --- Spinner ---

function Spinner() {
  return (
    <span
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent"
      aria-hidden
    />
  )
}

// --- Single stage row ---

function StageRow({ entry }: { entry: StageEntry }) {
  const label = STAGE_LABELS[entry.id] ?? entry.id

  if (entry.status === 'done') {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-300">
        <span className="text-emerald-400 w-4 text-center select-none">✓</span>
        <span>{label}</span>
      </div>
    )
  }

  if (entry.status === 'in-progress') {
    return (
      <div className="flex items-center gap-2 text-sm text-accent font-medium">
        <span className="w-4 flex items-center justify-center">
          <Spinner />
        </span>
        <span>{label}</span>
      </div>
    )
  }

  if (entry.status === 'error') {
    return (
      <div className="flex items-center gap-2 text-sm text-red-400">
        <span className="w-4 text-center select-none">✕</span>
        <span>{label}</span>
      </div>
    )
  }

  // pending — dim dot placeholder
  return (
    <div className="flex items-center gap-2 text-sm text-slate-600">
      <span className="w-4 text-center select-none">·</span>
      <span>{label}</span>
    </div>
  )
}

// --- Stock card ---

function StockCard({
  symbol,
  entries,
}: {
  symbol: string
  entries: StageEntry[]
}) {
  const title = `${symbol} · Deep Research`

  // Only render stages that have been seen (arrived via the stream).
  const seenIds = new Set(entries.map((e) => e.id))
  const visibleStages = STAGE_ORDER.filter((id) => seenIds.has(id)).map(
    (id) => entries.find((e) => e.id === id)!,
  )

  return (
    <div className="rounded-2xl rounded-bl-md border border-slate-line/60 bg-ink-700/70 px-4 py-3 flex flex-col gap-2">
      <p className="text-xs font-semibold tracking-wide text-slate-400 uppercase">
        {title}
      </p>
      <div className="flex flex-col gap-1.5">
        {visibleStages.map((entry) => (
          <StageRow key={entry.id} entry={entry} />
        ))}
      </div>
    </div>
  )
}

// --- Document analysis card ---

function DocCard({
  entries,
  filename,
}: {
  entries: StageEntry[]
  filename: string
}) {
  const title = `📄 ${filename} · 文档解读`

  const seenIds = new Set(entries.map((e) => e.id))
  const visibleStages = STAGE_ORDER.filter((id) => seenIds.has(id)).map(
    (id) => entries.find((e) => e.id === id)!,
  )

  return (
    <div className="rounded-2xl rounded-bl-md border border-slate-line/60 bg-ink-700/70 px-4 py-3 flex flex-col gap-2">
      <p className="text-xs font-semibold tracking-wide text-slate-400">
        {title}
      </p>
      <div className="flex flex-col gap-1.5">
        {visibleStages.map((entry) => (
          <StageRow key={entry.id} entry={entry} />
        ))}
      </div>
    </div>
  )
}

// --- Batch compare row (inline between stocks) ---

function BatchRow({ entries }: { entries: StageEntry[] }) {
  const compareEntry = entries.find((e) => e.id === 'compare')
  if (!compareEntry) return null

  return (
    <div className="flex items-center gap-3 px-1 py-0.5">
      <div className="h-px flex-1 bg-slate-line/40" />
      <div className="flex items-center gap-2 text-xs text-slate-500">
        {compareEntry.status === 'done' && (
          <span className="text-emerald-400">✓</span>
        )}
        {compareEntry.status === 'in-progress' && <Spinner />}
        {compareEntry.status === 'error' && (
          <span className="text-red-400">✕</span>
        )}
        <span>{STAGE_LABELS.compare}</span>
      </div>
      <div className="h-px flex-1 bg-slate-line/40" />
    </div>
  )
}

// --- Main component ---

interface ResearchProgressProps {
  progress: ResearchProgressState
  /** Currently uploaded document — provides the filename for the __doc__ track title. */
  uploadedDoc?: UploadedDoc | null
}

export default function ResearchProgress({ progress, uploadedDoc }: ResearchProgressProps) {
  const { order, stages } = progress

  if (order.length === 0) return null

  return (
    <div className="flex justify-start">
      <div className="flex flex-col gap-2 w-full max-w-sm">
        {order.map((symbol) => {
          const entries = stages[symbol] ?? []
          if (symbol === '__batch__') {
            return <BatchRow key={symbol} entries={entries} />
          }
          if (symbol === '__doc__') {
            const filename = uploadedDoc?.filename ?? '文档解读'
            return <DocCard key={symbol} entries={entries} filename={filename} />
          }
          return <StockCard key={symbol} symbol={symbol} entries={entries} />
        })}
      </div>
    </div>
  )
}
