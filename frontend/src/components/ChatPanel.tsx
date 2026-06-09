// Chat orchestration: a small reducer-driven state machine that owns the
// message list, optimistically echoes the user's turn, calls POST /chat/stream
// with the shared session id, and appends the agent's Markdown reply. While a
// Deep Research stream is in flight each stock gets a live stage-progress card;
// normal chat/analysis turns (no stage events) show the existing spinner.
// Token-by-token streaming: once the backend starts emitting token events the
// in-flight agent bubble is shown live, growing with each token.

import { useCallback, useReducer, useRef, useState } from 'react'
import { postChatStream } from '../lib/api'
import { useSessionId } from '../lib/SessionContext'
import type {
  ChatAction,
  ChatMessage,
  ChatState,
  ResearchProgressState,
  StageEntry,
  StageId,
  UploadedDoc,
} from '../lib/types'
import MessageList from './MessageList'
import Composer from './Composer'
import EmptyState from './EmptyState'
import ResearchProgress from './ResearchProgress'

function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'SEND_START':
      return {
        ...state,
        messages: [...state.messages, action.userMessage],
        status: 'sending',
        errorText: undefined,
      }
    case 'RETRY_START':
      return { ...state, status: 'sending', errorText: undefined }
    case 'SEND_SUCCESS':
      return {
        ...state,
        messages: [...state.messages, action.agentMessage],
        status: 'idle',
      }
    case 'SEND_ERROR':
      // Keep all prior messages; only surface a friendly error.
      return { ...state, status: 'error', errorText: action.errorText }
    case 'CLEAR_ERROR':
      return { ...state, status: 'idle', errorText: undefined }
    default:
      return state
  }
}

function newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 8)}`
}

const EMPTY_PROGRESS: ResearchProgressState = { order: [], stages: {} }

interface ChatPanelProps {
  onReportsReady?: () => void
}

export default function ChatPanel({ onReportsReady }: ChatPanelProps) {
  const sessionId = useSessionId()
  const [state, dispatch] = useReducer(chatReducer, {
    messages: [],
    status: 'idle',
  })
  // Remember the last user text so a failed turn can be retried.
  const lastUserText = useRef<string>('')
  const [draftSeed, setDraftSeed] = useState('')

  // Live research progress — cleared at the start of each send.
  const [progress, setProgress] = useState<ResearchProgressState>(EMPTY_PROGRESS)

  // Uploaded document state — set when Composer successfully uploads a file.
  const [uploadedDoc, setUploadedDoc] = useState<UploadedDoc | null>(null)

  // In-flight streaming agent bubble. Kept outside the reducer so token
  // appends don't trigger a full reducer cycle on every character.
  const [streamingMsg, setStreamingMsg] = useState<ChatMessage | null>(null)
  // Stable ref to the current streaming message id so the onToken closure
  // doesn't capture a stale id from the first render of this issue() call.
  const streamingIdRef = useRef<string | null>(null)

  // Issue the request and resolve the reply/error via the streaming endpoint.
  // Does NOT add the user bubble — callers control the optimistic echo so retry
  // won't duplicate it.
  const issue = useCallback(
    (text: string) => {
      // Reset progress and any prior streaming bubble for this new request.
      setProgress(EMPTY_PROGRESS)
      setStreamingMsg(null)
      streamingIdRef.current = null

      void postChatStream(sessionId, text, {
        onStage(ev) {
          setProgress((prev) => {
            const { symbol, stage, status } = ev
            const statusMapped: StageEntry['status'] =
              status === 'start'
                ? 'in-progress'
                : status === 'done'
                  ? 'done'
                  : 'error'

            // Add symbol to order if first-seen.
            const order = prev.order.includes(symbol)
              ? prev.order
              : [...prev.order, symbol]

            const existing = prev.stages[symbol] ?? []
            const entryIndex = existing.findIndex((e) => e.id === stage)

            let updated: StageEntry[]
            if (entryIndex === -1) {
              // First event for this (symbol, stage) pair.
              updated = [...existing, { id: stage as StageId, status: statusMapped }]
            } else {
              // Update existing entry in place.
              updated = existing.map((e, i) =>
                i === entryIndex ? { ...e, status: statusMapped } : e,
              )
            }

            return {
              order,
              stages: { ...prev.stages, [symbol]: updated },
            }
          })
        },

        onToken(text: string) {
          if (streamingIdRef.current === null) {
            // First token: create the in-flight bubble.
            const id = newId('a')
            streamingIdRef.current = id
            setStreamingMsg({ id, role: 'agent', content: text, streaming: true })
          } else {
            // Subsequent tokens: append to the existing bubble.
            setStreamingMsg((prev) =>
              prev
                ? { ...prev, content: prev.content + text }
                : { id: streamingIdRef.current!, role: 'agent', content: text, streaming: true },
            )
          }
        },

        onDone(ev) {
          // Finalize: replace the streaming bubble with the authoritative reply
          // from the done event, clear progress, and fire the report callback.
          setProgress(EMPTY_PROGRESS)
          const id = streamingIdRef.current ?? newId('a')
          streamingIdRef.current = null
          setStreamingMsg(null)
          dispatch({
            type: 'SEND_SUCCESS',
            agentMessage: { id, role: 'agent', content: ev.reply },
          })
          if (ev.reports && ev.reports.length > 0) {
            onReportsReady?.()
          }
        },

        onError(msg) {
          setProgress(EMPTY_PROGRESS)
          streamingIdRef.current = null
          setStreamingMsg(null)
          dispatch({ type: 'SEND_ERROR', errorText: msg })
        },
      })
    },
    [sessionId, onReportsReady],
  )

  const send = useCallback(
    (text: string) => {
      lastUserText.current = text
      dispatch({
        type: 'SEND_START',
        userMessage: { id: newId('u'), role: 'user', content: text },
      })
      issue(text)
    },
    [issue],
  )

  const retry = useCallback(() => {
    if (lastUserText.current) {
      // The user bubble is already present; re-issue without re-echoing.
      dispatch({ type: 'RETRY_START' })
      issue(lastUserText.current)
    } else {
      dispatch({ type: 'CLEAR_ERROR' })
    }
  }, [issue])

  const isBusy = state.status === 'sending'
  const isEmpty = state.messages.length === 0
  const hasProgress = progress.order.length > 0
  const isStreaming = streamingMsg !== null

  // While streaming tokens, show the growing bubble instead of the spinner /
  // progress card. During the stage phase (hasProgress, no tokens yet) show
  // the ResearchProgress card as before.
  const progressNode = isBusy
    ? isStreaming
      ? null // streaming bubble is rendered via streamingMsg prop below
      : hasProgress
        ? <ResearchProgress progress={progress} uploadedDoc={uploadedDoc} />
        : null
    : null

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
        <div className="mx-auto max-w-3xl">
          {isEmpty && state.status !== 'error' ? (
            <EmptyState
              variant="chat"
              onPickExample={(ex) => setDraftSeed(ex)}
            />
          ) : (
            <MessageList
              messages={state.messages}
              status={state.status}
              errorText={state.errorText}
              onRetry={retry}
              streamingMsg={isStreaming ? streamingMsg : null}
              progressNode={progressNode}
            />
          )}
        </div>
      </div>

      <div className="border-t border-slate-line/50 bg-ink-800/60 px-4 py-3 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <Composer
            key={draftSeed /* reseed textarea when an example is picked */}
            disabled={isBusy}
            onSend={send}
            initialText={draftSeed}
            onDocChange={setUploadedDoc}
          />
          <p className="mt-2 px-1 text-center text-[0.7rem] text-slate-500">
            回复由助手基于后端确定性计算生成 · 数字与结论均来自后端 · 仅供研究参考
          </p>
        </div>
      </div>
    </div>
  )
}
