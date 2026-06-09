// Shared types for the research console UI.
// The frontend performs no financial computation; every number, ranking, and
// conclusion originates in the backend reply or report. These types describe
// only transport shapes and local UI state.

/** A single chat turn rendered in the message stream. */
export interface ChatMessage {
  id: string
  role: 'user' | 'agent'
  /** Raw text from the user, or Markdown reply text from the agent. */
  content: string
  /** True while the agent is still streaming tokens into this message. */
  streaming?: boolean
}

/** POST /chat request body. */
export interface ChatRequest {
  session_id: string
  message: string
}

/** A report reference returned inline with a /chat response. */
export interface ChatReportRef {
  reportId: string
  title: string
  symbol: string
  downloadRef: string
}

/** POST /chat success body. */
export interface ChatResponse {
  reply: string
  reports?: ChatReportRef[]
}

/** A single item in the session report list (GET /report/{sid}). */
export interface ReportListItem {
  reportId: string
  title: string
  symbol: string
}

/** Chat panel state machine. */
export type ChatStatus = 'idle' | 'sending' | 'error'

export interface ChatState {
  messages: ChatMessage[]
  status: ChatStatus
  errorText?: string
}

export type ChatAction =
  | { type: 'SEND_START'; userMessage: ChatMessage }
  | { type: 'RETRY_START' }
  | { type: 'SEND_SUCCESS'; agentMessage: ChatMessage }
  | { type: 'SEND_ERROR'; errorText: string }
  | { type: 'CLEAR_ERROR' }

/**
 * Result of GET /report/{session_id}/{report_id}, normalized by the api layer
 * so callers can distinguish "not found" (404) from a transport error.
 */
export type ReportFetch =
  | { kind: 'ready'; markdown: string }
  | { kind: 'empty' } // backend 404 → no such report
  | { kind: 'error'; text: string }

/** Report panel state machine — models list and detail views. */
export type ReportState =
  | { kind: 'idle' }
  | { kind: 'loading-list' }
  | { kind: 'list'; items: ReportListItem[] }
  | { kind: 'empty' }
  | { kind: 'loading-detail'; item: ReportListItem }
  | { kind: 'detail'; item: ReportListItem; markdown: string }
  | { kind: 'error'; text: string }

// ---------------------------------------------------------------------------
// Deep Research streaming types
// ---------------------------------------------------------------------------

/** Canonical stage ids emitted by POST /chat/stream. */
export type StageId =
  | 'identify'
  | 'market_data'
  | 'metrics'
  | 'risk'
  | 'compare'
  | 'chart'
  | 'events'
  | 'filings'
  | 'risk_factors'
  | 'assemble'
  | 'doc_load'
  | 'doc_parse'
  | 'doc_locate'
  | 'doc_summarize'

/** Chinese display labels for each stage. */
export const STAGE_LABELS: Record<StageId, string> = {
  identify: '识别公司',
  market_data: '取行情日线',
  metrics: '计算指标',
  risk: '评估市场风险',
  compare: '横向比较排名',
  chart: '渲染走势图',
  events: '检索相关事件',
  filings: '拉取 SEC 申报',
  risk_factors: '提取经营风险',
  assemble: '组装报告',
  doc_load: '读取文件',
  doc_parse: '解析并建立索引（向量化）',
  doc_locate: '定位相关内容',
  doc_summarize: '理解并汇总',
}

/** Canonical order for rendering stages. */
export const STAGE_ORDER: StageId[] = [
  'identify',
  'market_data',
  'metrics',
  'risk',
  'compare',
  'chart',
  'events',
  'filings',
  'risk_factors',
  'assemble',
  'doc_load',
  'doc_parse',
  'doc_locate',
  'doc_summarize',
]

/** An uploaded document that has been accepted by the backend. */
export interface UploadedDoc {
  filename: string
  pages: number
  chars: number
  indexTruncated?: boolean
}

/** A phase event streamed during POST /upload (NDJSON). */
export interface UploadPhaseEvent {
  phase: string
  label: string
  done?: number
  total?: number
}

/** A single stage event from the NDJSON stream. */
export interface StageEvent {
  type: 'stage'
  symbol: string
  stage: StageId
  status: 'start' | 'done' | 'error'
}

/** The terminal done event from the NDJSON stream. */
export interface DoneEvent {
  type: 'done'
  reply: string
  reports: ChatReportRef[] | null
}

/** An error event from the NDJSON stream. */
export interface StreamErrorEvent {
  type: 'error'
  message: string
}

/** Per-stage status inside the live progress state. */
export type StageStatus = 'pending' | 'in-progress' | 'done' | 'error'

/** One stage entry stored in progress state. */
export interface StageEntry {
  id: StageId
  status: StageStatus
}

/** Live progress state for all symbols being researched. */
export interface ResearchProgressState {
  /** Symbols in first-seen order (may include "__batch__"). */
  order: string[]
  /** Map from symbol -> ordered array of seen stages. */
  stages: Record<string, StageEntry[]>
}

/** A normalized API failure (non-404). */
export class ApiError extends Error {
  readonly status?: number
  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}
