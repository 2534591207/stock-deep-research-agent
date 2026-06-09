// Application root. Generates the one client session id for this tab, provides
// it read-only to the tree, and lays out the three regions: a persistent
// disclosure bar, the chat panel, and an on-demand report viewer overlay.

import { useMemo, useState } from 'react'
import { getSessionId } from './lib/session'
import { SessionProvider } from './lib/SessionContext'
import AppHeader from './components/AppHeader'
import DisclosureBar from './components/DisclosureBar'
import ChatPanel from './components/ChatPanel'
import ReportPanel from './components/ReportPanel'

export default function App() {
  // One id per tab, created once; not persisted across refreshes.
  const sessionId = useMemo(() => getSessionId(), [])
  const [reportOpen, setReportOpen] = useState(false)

  return (
    <SessionProvider value={sessionId}>
      <div className="flex h-full flex-col bg-ink-900">
        <AppHeader onOpenReport={() => setReportOpen(true)} />
        <DisclosureBar />

        <main className="min-h-0 flex-1">
          <ChatPanel onReportsReady={() => setReportOpen(true)} />
        </main>

        <ReportPanel open={reportOpen} onClose={() => setReportOpen(false)} />
      </div>
    </SessionProvider>
  )
}
