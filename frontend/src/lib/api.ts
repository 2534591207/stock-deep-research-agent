// Thin fetch wrapper around the backend endpoints.
//
//   POST /chat                        -> { reply, reports? }
//   GET  /report/{session_id}         -> { reports: [...] }  (list, newest first)
//   GET  /report/{session_id}/{id}    -> text/markdown
//   GET  /report/{session_id}/latest  -> text/markdown (404 when none yet)
//   GET  /health                      -> { ok: true }
//
// Error normalization is the key responsibility: a 404 on the report endpoint
// means "not found yet" (an empty state, not a failure), while 5xx / network
// problems are surfaced as errors so the UI can show a friendly retryable
// notice. The frontend never invents data on failure.

import {
  ApiError,
  type ChatResponse,
  type ChatReportRef,
  type DoneEvent,
  type ReportFetch,
  type ReportListItem,
  type StageEvent,
  type UploadPhaseEvent,
} from './types'

/** Backend base URL. Configurable via env; defaults to local dev backend. */
export const API_BASE: string = normalizeBase(
  import.meta.env.VITE_API_BASE as string | undefined,
)

function normalizeBase(raw: string | undefined): string {
  const value = (raw ?? '').trim()
  const base = value.length > 0 ? value : 'http://localhost:8000'
  return base.replace(/\/+$/, '')
}

/** POST /chat — send one user turn, return the agent reply and optional report refs. */
export async function postChat(
  sessionId: string,
  message: string,
): Promise<ChatResponse> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    })
  } catch {
    throw new ApiError('网络连接失败，请确认服务已启动后重试。')
  }

  if (!res.ok) {
    throw new ApiError(`服务暂时无法响应（${res.status}），请稍后再试。`, res.status)
  }

  let data: unknown
  try {
    data = await res.json()
  } catch {
    throw new ApiError('收到的响应无法解析，请稍后再试。')
  }

  const reply = (data as { reply?: unknown } | null)?.reply
  if (typeof reply !== 'string') {
    throw new ApiError('响应缺少回复内容，请稍后再试。')
  }

  // Defensively parse optional reports array (snake_case -> camelCase).
  const rawReports = (data as { reports?: unknown } | null)?.reports
  if (Array.isArray(rawReports) && rawReports.length > 0) {
    const refs: ChatReportRef[] = []
    for (const item of rawReports) {
      if (
        item !== null &&
        typeof item === 'object' &&
        typeof (item as Record<string, unknown>).report_id === 'string' &&
        typeof (item as Record<string, unknown>).title === 'string' &&
        typeof (item as Record<string, unknown>).symbol === 'string' &&
        typeof (item as Record<string, unknown>).download_ref === 'string'
      ) {
        const r = item as {
          report_id: string
          title: string
          symbol: string
          download_ref: string
        }
        refs.push({
          reportId: r.report_id,
          title: r.title,
          symbol: r.symbol,
          downloadRef: r.download_ref,
        })
      }
    }
    if (refs.length > 0) {
      return { reply, reports: refs }
    }
  }

  return { reply }
}

/** Handlers passed to postChatStream. */
export interface ChatStreamHandlers {
  onStage: (ev: StageEvent) => void
  onToken: (text: string) => void
  onDone: (ev: DoneEvent) => void
  onError: (message: string) => void
}

/**
 * POST /chat/stream — send one user turn and stream stage-progress + done events
 * as application/x-ndjson. Each newline-delimited JSON object is dispatched to
 * the appropriate handler. Handles multi-line chunks and a trailing partial line
 * in the read buffer. On network failure, onError is called with a friendly message.
 * snake_case fields in the done event's reports are mapped to camelCase.
 */
export async function postChatStream(
  sessionId: string,
  message: string,
  handlers: ChatStreamHandlers,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    })
  } catch {
    handlers.onError('网络连接失败，请确认服务已启动后重试。')
    return
  }

  if (!res.ok) {
    handlers.onError(`服务暂时无法响应（${res.status}），请稍后再试。`)
    return
  }

  if (!res.body) {
    handlers.onError('收到的响应无法读取，请稍后再试。')
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatchLine = (line: string) => {
    const trimmed = line.trim()
    if (!trimmed) return
    let obj: unknown
    try {
      obj = JSON.parse(trimmed)
    } catch {
      return // skip malformed line
    }
    if (obj === null || typeof obj !== 'object') return
    const ev = obj as Record<string, unknown>
    if (ev.type === 'stage') {
      handlers.onStage(ev as unknown as StageEvent)
    } else if (ev.type === 'token') {
      if (typeof ev.text === 'string') {
        handlers.onToken(ev.text)
      }
    } else if (ev.type === 'done') {
      // Normalize snake_case report fields to camelCase.
      const rawReports = ev.reports
      let reports: ChatReportRef[] | null = null
      if (Array.isArray(rawReports) && rawReports.length > 0) {
        const refs: ChatReportRef[] = []
        for (const item of rawReports) {
          if (
            item !== null &&
            typeof item === 'object' &&
            typeof (item as Record<string, unknown>).report_id === 'string' &&
            typeof (item as Record<string, unknown>).title === 'string' &&
            typeof (item as Record<string, unknown>).symbol === 'string' &&
            typeof (item as Record<string, unknown>).download_ref === 'string'
          ) {
            const r = item as {
              report_id: string
              title: string
              symbol: string
              download_ref: string
            }
            refs.push({
              reportId: r.report_id,
              title: r.title,
              symbol: r.symbol,
              downloadRef: r.download_ref,
            })
          }
        }
        if (refs.length > 0) reports = refs
      }
      handlers.onDone({
        type: 'done',
        reply: typeof ev.reply === 'string' ? ev.reply : '',
        reports,
      })
    } else if (ev.type === 'error') {
      handlers.onError(
        typeof ev.message === 'string' ? ev.message : '流式响应出错，请稍后再试。',
      )
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        // Flush any trailing partial line (no trailing newline).
        if (buffer.trim()) dispatchLine(buffer)
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // Keep the last element as the (possibly incomplete) partial line.
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        dispatchLine(line)
      }
    }
  } catch {
    handlers.onError('读取响应时发生网络错误，请稍后再试。')
  }
}

/**
 * GET /report/{sessionId} — fetch the list of reports for this session.
 * 200 with array  -> { kind: 'ready', items }
 * 200 empty array -> { kind: 'ready', items: [] }  (caller shows empty state)
 * 404             -> { kind: 'empty' }
 * otherwise       -> { kind: 'error' }
 */
export async function listReports(
  sessionId: string,
): Promise<{ kind: 'ready'; items: ReportListItem[] } | { kind: 'empty' } | { kind: 'error'; text: string }> {
  let res: Response
  try {
    res = await fetch(
      `${API_BASE}/report/${encodeURIComponent(sessionId)}`,
      { headers: { Accept: 'application/json' } },
    )
  } catch {
    return { kind: 'error', text: '网络连接失败，请确认服务已启动后重试。' }
  }

  if (res.status === 404) {
    return { kind: 'empty' }
  }
  if (!res.ok) {
    return { kind: 'error', text: `获取报告列表失败（${res.status}），请稍后再试。` }
  }

  let data: unknown
  try {
    data = await res.json()
  } catch {
    return { kind: 'error', text: '报告列表响应无法解析，请稍后再试。' }
  }

  const rawList = (data as { reports?: unknown } | null)?.reports
  if (!Array.isArray(rawList)) {
    return { kind: 'ready', items: [] }
  }

  const items: ReportListItem[] = []
  for (const item of rawList) {
    if (
      item !== null &&
      typeof item === 'object' &&
      typeof (item as Record<string, unknown>).report_id === 'string' &&
      typeof (item as Record<string, unknown>).title === 'string' &&
      typeof (item as Record<string, unknown>).symbol === 'string'
    ) {
      const r = item as { report_id: string; title: string; symbol: string }
      items.push({ reportId: r.report_id, title: r.title, symbol: r.symbol })
    }
  }

  return { kind: 'ready', items }
}

/**
 * GET /report/{sessionId}/{reportId} — fetch one report's markdown.
 * 200 -> { kind: 'ready', markdown }; 404 -> { kind: 'empty' };
 * otherwise -> { kind: 'error' }. Chart image references are rewritten so
 * the browser can load them from the backend (absolute URLs are left untouched).
 */
export async function getReport(
  sessionId: string,
  reportId: string,
): Promise<ReportFetch> {
  let res: Response
  try {
    res = await fetch(
      `${API_BASE}/report/${encodeURIComponent(sessionId)}/${encodeURIComponent(reportId)}`,
      { headers: { Accept: 'text/markdown, text/plain' } },
    )
  } catch {
    return { kind: 'error', text: '网络连接失败，请确认服务已启动后重试。' }
  }

  if (res.status === 404) {
    return { kind: 'empty' }
  }
  if (!res.ok) {
    return { kind: 'error', text: `获取报告失败（${res.status}），请稍后再试。` }
  }

  const raw = await res.text()
  return { kind: 'ready', markdown: rewriteReportImages(raw) }
}

/**
 * GET /report/{sessionId}/latest — fetch this session's latest report markdown.
 * Kept for back-compat; prefer getReport() for specific reports.
 * 200 -> { kind: 'ready', markdown }; 404 -> { kind: 'empty' };
 * otherwise -> { kind: 'error' }.
 */
export async function getLatestReport(sessionId: string): Promise<ReportFetch> {
  let res: Response
  try {
    res = await fetch(
      `${API_BASE}/report/${encodeURIComponent(sessionId)}/latest`,
      { headers: { Accept: 'text/markdown, text/plain' } },
    )
  } catch {
    return { kind: 'error', text: '网络连接失败，请确认服务已启动后重试。' }
  }

  if (res.status === 404) {
    return { kind: 'empty' }
  }
  if (!res.ok) {
    return {
      kind: 'error',
      text: `获取报告失败（${res.status}），请稍后再试。`,
    }
  }

  const raw = await res.text()
  return { kind: 'ready', markdown: rewriteReportImages(raw) }
}

/**
 * POST /upload — upload a financial document for the current session.
 * The backend streams application/x-ndjson progress events during indexing:
 *   {"type":"phase","phase":"extract","label":"读取并解析文件"}
 *   {"type":"phase","phase":"index","label":"建立向量索引","done":40,"total":83}
 *   {"type":"ready","filename":...,"pages":...,"chars":...,"index_truncated":...}
 *   {"type":"error","message":"..."}
 * Pre-stream HTTP errors: 415 (unsupported type), 413 (too large) are mapped
 * to friendly messages. `onPhase` is called for each phase event so the UI
 * can show live progress.
 */
export async function uploadDocument(
  sessionId: string,
  file: File,
  onPhase?: (ev: UploadPhaseEvent) => void,
): Promise<
  | { kind: 'ready'; filename: string; pages: number; chars: number; indexTruncated: boolean }
  | { kind: 'error'; text: string }
> {
  const form = new FormData()
  form.append('file', file)
  form.append('session_id', sessionId)

  let res: Response
  try {
    res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form })
  } catch {
    return { kind: 'error', text: '网络连接失败，请确认服务已启动后重试。' }
  }

  if (res.status === 415) {
    return { kind: 'error', text: '不支持的文件类型，请上传 PDF/TXT/MD' }
  }
  if (res.status === 413) {
    return { kind: 'error', text: '文件过大，请上传较小的文件后重试。' }
  }
  if (!res.ok) {
    return { kind: 'error', text: `上传失败（${res.status}），请稍后再试。` }
  }

  // Streaming path: backend returns application/x-ndjson
  if (!res.body) {
    return { kind: 'error', text: '上传响应无法读取，请稍后再试。' }
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const parseLine = (
    line: string,
  ):
    | { kind: 'ready'; filename: string; pages: number; chars: number; indexTruncated: boolean }
    | { kind: 'error'; text: string }
    | null => {
    const trimmed = line.trim()
    if (!trimmed) return null
    let obj: unknown
    try {
      obj = JSON.parse(trimmed)
    } catch {
      return null // skip malformed line
    }
    if (obj === null || typeof obj !== 'object') return null
    const ev = obj as Record<string, unknown>

    if (ev.type === 'phase') {
      if (onPhase) {
        onPhase({
          phase: typeof ev.phase === 'string' ? ev.phase : '',
          label: typeof ev.label === 'string' ? ev.label : '',
          done: typeof ev.done === 'number' ? ev.done : undefined,
          total: typeof ev.total === 'number' ? ev.total : undefined,
        })
      }
      return null
    }

    if (ev.type === 'ready') {
      if (
        typeof ev.filename === 'string' &&
        typeof ev.pages === 'number' &&
        typeof ev.chars === 'number'
      ) {
        return {
          kind: 'ready',
          filename: ev.filename,
          pages: ev.pages,
          chars: ev.chars,
          indexTruncated: ev.index_truncated === true,
        }
      }
      return { kind: 'error', text: '上传响应格式不正确，请稍后再试。' }
    }

    if (ev.type === 'error') {
      return {
        kind: 'error',
        text: typeof ev.message === 'string' ? ev.message : '上传处理出错，请稍后再试。',
      }
    }

    return null
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        // Flush trailing partial line (no trailing newline).
        if (buffer.trim()) {
          const result = parseLine(buffer)
          if (result) return result
        }
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // Keep the last element as the (possibly incomplete) partial line.
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        const result = parseLine(line)
        if (result) return result
      }
    }
  } catch {
    return { kind: 'error', text: '读取上传响应时发生网络错误，请稍后再试。' }
  }

  return { kind: 'error', text: '上传响应未包含结果，请稍后再试。' }
}

/** GET /health — lightweight reachability probe. */
export async function getHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`)
    if (!res.ok) return false
    const data = (await res.json()) as { ok?: unknown }
    return data?.ok === true
  } catch {
    return false
  }
}

/**
 * Report markdown may reference the price-trend chart by its server-side file
 * path (it is written under the backend's `_reports/` directory). A browser
 * cannot read a local filesystem path, so any such reference is rewritten to
 * the backend's HTTP-served static path. References that are already absolute
 * URLs or data URIs are left untouched. The MarkdownView still provides a
 * graceful fallback if an image fails to load.
 */
export function rewriteReportImages(markdown: string): string {
  // Matches Markdown image syntax: ![alt](target)
  return markdown.replace(
    /(!\[[^\]]*\]\()([^)]+)(\))/g,
    (whole, prefix: string, target: string, suffix: string) => {
      const url = target.trim()
      if (/^(https?:|data:)/i.test(url)) {
        return whole // already browser-loadable
      }
      // Take the file name after the last path separator and serve it from the
      // backend's static reports mount.
      const fileName = url.split(/[/\\]/).pop()
      if (!fileName) return whole
      return `${prefix}${API_BASE}/reports/${fileName}${suffix}`
    },
  )
}
