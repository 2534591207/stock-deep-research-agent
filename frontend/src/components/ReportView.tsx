// Report rich-text presentation. Reuses the shared MarkdownView so the 9
// sections, tables, verbatim disclaimer, and the price-trend chart all render
// through one pipeline. Degraded sections ("insufficient evidence / section
// unavailable") and the verbatim disclaimer are shown exactly as the backend
// produced them — never hidden, paraphrased, or filled with placeholder data.

import MarkdownView from './MarkdownView'

interface ReportViewProps {
  markdown: string
}

export default function ReportView({ markdown }: ReportViewProps) {
  return (
    <article className="mx-auto max-w-3xl">
      <MarkdownView content={markdown} />
    </article>
  )
}
