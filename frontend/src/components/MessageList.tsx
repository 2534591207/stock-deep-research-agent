// Ordered message stream that auto-scrolls to the latest turn. Shows the
// agent "thinking" indicator inline while a reply is in flight, and a friendly
// error notice (with retry) without dropping any prior messages.

import { useEffect, useRef } from 'react'
import type React from 'react'
import type { ChatMessage, ChatStatus } from '../lib/types'
import MessageBubble from './MessageBubble'
import LoadingIndicator from './LoadingIndicator'
import ErrorNotice from './ErrorNotice'

interface MessageListProps {
  messages: ChatMessage[]
  status: ChatStatus
  errorText?: string
  onRetry?: () => void
  /** Optional node rendered in place of the default spinner while sending. */
  progressNode?: React.ReactNode
  /** In-flight streaming agent bubble; rendered after committed messages. */
  streamingMsg?: ChatMessage | null
}

export default function MessageList({
  messages,
  status,
  errorText,
  onRetry,
  progressNode,
  streamingMsg,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, status, streamingMsg])

  return (
    <div className="flex flex-col gap-4">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}

      {/* Live streaming bubble — shown while tokens are arriving */}
      {streamingMsg && (
        <MessageBubble key={streamingMsg.id} message={streamingMsg} />
      )}

      {status === 'sending' && !streamingMsg && (
        progressNode ?? (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md border border-slate-line/60 bg-ink-700/70 px-4 py-3">
              <LoadingIndicator label="助手正在分析…" />
            </div>
          </div>
        )
      )}

      {status === 'error' && errorText && (
        <ErrorNotice message={errorText} onRetry={onRetry} />
      )}

      <div ref={bottomRef} />
    </div>
  )
}
