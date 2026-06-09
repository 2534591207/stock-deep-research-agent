// The single controlled rich-text pipeline, shared by chat bubbles and the
// report viewer. Markdown is parsed by react-markdown (with GFM tables and
// line breaks) — never injected as raw HTML — so untrusted text cannot run
// scripts. Images get a custom renderer that degrades gracefully when the
// referenced chart is not reachable, so the report stays readable.

import { useState, type ComponentPropsWithoutRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownViewProps {
  content: string
  className?: string
}

/** Image renderer with a calm, non-breaking fallback on load failure. */
function MarkdownImage({ src, alt }: ComponentPropsWithoutRef<'img'>) {
  const [failed, setFailed] = useState(false)
  const label = (typeof alt === 'string' && alt) || '走势图'

  if (failed || !src || typeof src !== 'string') {
    return (
      <span className="my-3 flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-line/70 bg-ink-700/40 px-4 py-6 text-center text-sm text-slate-400">
        <span aria-hidden className="text-lg opacity-70">
          ◌
        </span>
        <span>{label}暂不可显示</span>
        <span className="text-xs text-slate-500">
          图表由后端生成；若未接入静态资源则此处显示占位
        </span>
      </span>
    )
  }

  return (
    <img
      src={src}
      alt={label}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

export default function MarkdownView({ content, className }: MarkdownViewProps) {
  return (
    <div className={`rich ${className ?? ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: MarkdownImage,
          // External links open safely in a new tab.
          a: ({ href, children, ...rest }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              {...rest}
            >
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
