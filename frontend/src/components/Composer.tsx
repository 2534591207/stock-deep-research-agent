// Input affordance: a growing textarea plus a send control. Enforces input
// discipline — empty/whitespace-only submissions are ignored, and while a
// request is in flight the control is disabled so a turn cannot be sent twice.
// Enter sends; Shift+Enter inserts a newline.
//
// Also provides a 📎 attach control for uploading a single financial document
// (PDF/TXT/MD) to the session. Upload state is kept locally; a chip shows the
// ready filename, and errors are surfaced inline. The send flow is unaffected.

import {
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ChangeEvent,
} from 'react'
import { uploadDocument } from '../lib/api'
import { useSessionId } from '../lib/SessionContext'
import type { UploadedDoc, UploadPhaseEvent } from '../lib/types'

interface ComposerProps {
  disabled: boolean
  onSend: (text: string) => void
  /** Optional seed text (e.g. an example prompt the user tapped). */
  initialText?: string
  /** Called when a document has been successfully uploaded, or cleared. */
  onDocChange?: (doc: UploadedDoc | null) => void
}

export default function Composer({
  disabled,
  onSend,
  initialText = '',
  onDocChange,
}: ComposerProps) {
  const sessionId = useSessionId()
  const [value, setValue] = useState(initialText)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Upload state:
  //   null       = no doc
  //   { phase }  = in-flight with live phase info
  //   UploadedDoc = ready
  //   string     = error message
  const [docState, setDocState] = useState<
    null | { uploading: true; phase: UploadPhaseEvent | null } | UploadedDoc | string
  >(null)

  const submit = () => {
    const trimmed = value.trim()
    if (trimmed.length === 0 || disabled) return
    onSend(trimmed)
    setValue('')
    // Reset the auto-grown height after sending.
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    submit()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const autoGrow = (el: HTMLTextAreaElement) => {
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    // Reset input so the same file can be re-selected after removal.
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (!file) return

    setDocState({ uploading: true, phase: null })
    onDocChange?.(null)

    const result = await uploadDocument(sessionId, file, (ev) => {
      setDocState({ uploading: true, phase: ev })
    })

    if (result.kind === 'ready') {
      const doc: UploadedDoc = {
        filename: result.filename,
        pages: result.pages,
        chars: result.chars,
        indexTruncated: result.indexTruncated,
      }
      setDocState(doc)
      onDocChange?.(doc)
    } else {
      setDocState(result.text)
      onDocChange?.(null)
    }
  }

  const clearDoc = () => {
    setDocState(null)
    onDocChange?.(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const canSend = value.trim().length > 0 && !disabled

  const isUploading = docState !== null && typeof docState === 'object' && 'uploading' in docState
  const isError = typeof docState === 'string'
  const isReady = docState !== null && !isUploading && !isError

  // Derive the live phase label for the uploading state.
  const uploadingPhase = isUploading
    ? (docState as { uploading: true; phase: UploadPhaseEvent | null }).phase
    : null
  const uploadLabel = (() => {
    if (!uploadingPhase) return '上传中…'
    if (uploadingPhase.phase === 'index' && uploadingPhase.done != null && uploadingPhase.total != null) {
      return `${uploadingPhase.label} ${uploadingPhase.done}/${uploadingPhase.total}`
    }
    return uploadingPhase.label
  })()

  const readyDoc = isReady ? (docState as UploadedDoc) : null

  return (
    <div className="flex flex-col gap-1.5">
      {/* Document status row — only shown when there is something to show */}
      {docState !== null && (
        <div className="flex items-center gap-2 px-1">
          {isUploading && (
            <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
              {/* Animated spinner */}
              <svg
                className="h-3 w-3 animate-spin text-accent"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                />
              </svg>
              <span>{uploadLabel}</span>
            </span>
          )}
          {isReady && readyDoc && (
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-line/60 bg-ink-700/80 px-2.5 py-1 text-xs text-slate-300">
              <span>📄</span>
              <span className="max-w-[200px] truncate">
                {readyDoc.filename}（已就绪）{readyDoc.indexTruncated ? '· 仅索引前部分' : ''}
              </span>
              <button
                type="button"
                onClick={clearDoc}
                aria-label="移除文件"
                className="ml-0.5 text-slate-500 hover:text-slate-200 transition"
              >
                ✕
              </button>
            </span>
          )}
          {isError && (
            <span className="text-xs text-red-400">{docState as string}</span>
          )}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 rounded-2xl border border-slate-line/70 bg-ink-700/80 p-2 shadow-lg shadow-black/20 focus-within:border-accent/60"
      >
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md"
          className="hidden"
          onChange={handleFileChange}
        />

        {/* Attach button */}
        <button
          type="button"
          disabled={disabled || isUploading}
          aria-label="附加文件"
          onClick={() => fileInputRef.current?.click()}
          className="flex h-10 shrink-0 items-center justify-center rounded-xl px-2.5 text-slate-400 transition hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
          title="上传 PDF/TXT/MD 文档"
        >
          <span aria-hidden>📎</span>
        </button>

        <textarea
          ref={textareaRef}
          value={value}
          rows={1}
          onChange={(e) => {
            setValue(e.target.value)
            autoGrow(e.target)
          }}
          onKeyDown={handleKeyDown}
          placeholder="用大白话提问，例如：分析下英伟达最近三个月…"
          className="max-h-[180px] flex-1 resize-none bg-transparent px-2.5 py-2 text-[0.95rem] leading-relaxed text-slate-100 placeholder:text-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={!canSend}
          aria-label="发送"
          className="flex h-10 shrink-0 items-center gap-1.5 rounded-xl bg-accent px-4 text-sm font-medium text-white transition enabled:hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span>发送</span>
          <span aria-hidden>↑</span>
        </button>
      </form>
    </div>
  )
}
