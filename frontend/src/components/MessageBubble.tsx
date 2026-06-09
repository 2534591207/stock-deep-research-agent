// One chat turn. User turns render as plain text (right-aligned, accent
// surface). Agent turns render their Markdown through the shared MarkdownView
// so the reply's headings, lists, tables and emphasis read cleanly. Honest
// replies (unrecognized ticker, insufficient evidence) are shown verbatim in
// the same neutral surface — never restyled into an alarming error.
// When message.streaming is true a blinking cursor is appended to signal that
// tokens are still arriving.

import type { ChatMessage } from '../lib/types'
import MarkdownView from './MarkdownView'

interface MessageBubbleProps {
  message: ChatMessage
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={`flex animate-fade-rise ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={
          isUser
            ? 'max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-accent-soft/80 px-4 py-2.5 text-[0.95rem] leading-relaxed text-slate-50 ring-1 ring-accent/30 sm:max-w-[75%]'
            : 'max-w-[92%] rounded-2xl rounded-bl-md border border-slate-line/60 bg-ink-700/70 px-4 py-3 sm:max-w-[82%]'
        }
      >
        {isUser ? (
          <span>{message.content}</span>
        ) : (
          <div className="relative">
            <MarkdownView content={message.content} />
            {message.streaming && (
              <span
                aria-hidden="true"
                className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[0.1em] animate-pulse rounded-sm bg-slate-400 align-middle"
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
