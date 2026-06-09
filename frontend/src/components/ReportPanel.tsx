// Report viewer rendered as an overlay panel/drawer.
// State machine:
//   loading-list  -> fetching the session's report list
//   list          -> showing the list of reports (click to drill in)
//   empty         -> session has no reports yet (backend 404 or empty list)
//   loading-detail -> fetching a single report's markdown
//   detail        -> showing one report's markdown with back/download controls
//   error         -> a friendly, retryable notice (5xx / network)

import { useCallback, useEffect, useState } from 'react'
import { listReports, getReport } from '../lib/api'
import { useSessionId } from '../lib/SessionContext'
import type { ReportListItem, ReportState } from '../lib/types'
import ReportView from './ReportView'
import EmptyState from './EmptyState'
import LoadingIndicator from './LoadingIndicator'
import ErrorNotice from './ErrorNotice'

interface ReportPanelProps {
  open: boolean
  onClose: () => void
}

export default function ReportPanel({ open, onClose }: ReportPanelProps) {
  const sessionId = useSessionId()
  const [state, setState] = useState<ReportState>({ kind: 'idle' })

  const loadList = useCallback(async () => {
    setState({ kind: 'loading-list' })
    const result = await listReports(sessionId)
    if (result.kind === 'ready') {
      if (result.items.length === 0) {
        setState({ kind: 'empty' })
      } else {
        setState({ kind: 'list', items: result.items })
      }
    } else if (result.kind === 'empty') {
      setState({ kind: 'empty' })
    } else {
      setState({ kind: 'error', text: result.text })
    }
  }, [sessionId])

  const loadDetail = useCallback(async (item: ReportListItem) => {
    setState({ kind: 'loading-detail', item })
    const result = await getReport(sessionId, item.reportId)
    if (result.kind === 'ready') {
      setState({ kind: 'detail', item, markdown: result.markdown })
    } else if (result.kind === 'empty') {
      setState({ kind: 'error', text: '该报告不存在，请刷新列表后重试。' })
    } else {
      setState({ kind: 'error', text: result.text })
    }
  }, [sessionId])

  // Fetch the list whenever the panel opens.
  useEffect(() => {
    if (open) {
      void loadList()
    }
  }, [open, loadList])

  // Close on Escape for keyboard accessibility.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  // Determine header controls based on state.
  const isLoading = state.kind === 'loading-list' || state.kind === 'loading-detail'
  const inDetail = state.kind === 'detail'
  const inList = state.kind === 'list'

  function downloadDetail() {
    if (state.kind !== 'detail') return
    const blob = new Blob([state.markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${state.item.symbol}-report.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-30 flex" role="dialog" aria-modal="true" aria-label="研究报告">
      {/* Scrim */}
      <button
        type="button"
        aria-label="关闭报告"
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />

      {/* Panel: right drawer on wide screens, full-width on narrow screens */}
      <div className="relative ml-auto flex h-full w-full flex-col border-l border-slate-line/60 bg-ink-800 shadow-2xl shadow-black/50 md:max-w-2xl lg:max-w-3xl animate-fade-rise">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-slate-line/60 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2">
            {inDetail && (
              <button
                type="button"
                onClick={() => void loadList()}
                className="mr-1 flex items-center gap-1 rounded-lg border border-slate-line/70 bg-ink-700 px-2.5 py-1.5 text-xs font-medium text-slate-200 transition hover:border-accent/50 hover:bg-ink-600"
              >
                ← 返回列表
              </button>
            )}
            <span aria-hidden className="text-slate-400">▤</span>
            <h2 className="text-base font-semibold text-slate-100">
              {inDetail ? state.item.title : '研究报告'}
            </h2>
            {inDetail && (
              <span className="hidden text-xs text-slate-500 sm:inline">
                · {state.item.symbol}
              </span>
            )}
            {!inDetail && (
              <span className="hidden text-xs text-slate-500 sm:inline">
                · 本会话报告列表
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {inDetail && (
              <button
                type="button"
                onClick={downloadDetail}
                className="rounded-lg border border-slate-line/70 bg-ink-700 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-accent/50 hover:bg-ink-600"
              >
                下载 Markdown
              </button>
            )}
            {(inList || state.kind === 'empty' || state.kind === 'error') && (
              <button
                type="button"
                onClick={() => void loadList()}
                disabled={isLoading}
                className="rounded-lg border border-slate-line/70 bg-ink-700 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-accent/50 hover:bg-ink-600 disabled:opacity-50"
              >
                刷新
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-line/70 bg-ink-700 text-slate-300 transition hover:border-accent/50 hover:bg-ink-600"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          {(state.kind === 'loading-list' || state.kind === 'loading-detail') && (
            <div className="flex h-full items-center justify-center">
              <LoadingIndicator
                label={state.kind === 'loading-list' ? '正在加载报告列表…' : '正在加载报告…'}
              />
            </div>
          )}

          {state.kind === 'empty' && <EmptyState variant="report" />}

          {state.kind === 'error' && (
            <div className="mx-auto max-w-md py-10">
              <ErrorNotice message={state.text} onRetry={() => void loadList()} />
            </div>
          )}

          {state.kind === 'list' && (
            <ul className="mx-auto max-w-3xl divide-y divide-slate-line/40">
              {state.items.map((item) => (
                <li key={item.reportId}>
                  <button
                    type="button"
                    onClick={() => void loadDetail(item)}
                    className="flex w-full items-center justify-between gap-4 px-1 py-3.5 text-left transition hover:bg-ink-700/50 rounded-lg"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-slate-100">
                        {item.title}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-400">{item.symbol}</p>
                    </div>
                    <span className="shrink-0 text-slate-500 text-xs">查看 →</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {state.kind === 'detail' && <ReportView markdown={state.markdown} />}
        </div>

        <div className="border-t border-slate-line/50 bg-ink-800/80 px-4 py-2.5 text-[0.7rem] leading-relaxed text-slate-500 sm:px-6">
          报告由后端基于 Yahoo Finance 延迟日线确定性生成；含逐字英文免责声明（原样展示）。
          外部来源（新闻 / SEC 申报）不可用时该节诚实降级，核心行情分析照常。
        </div>
      </div>
    </div>
  )
}
