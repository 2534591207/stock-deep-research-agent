// Read-only context that provides the one client session id to the tree.
// Created once in App via getSessionId(); both the chat and report panels read
// the same id so every /chat call and every report fetch share one session.

import { createContext, useContext } from 'react'

const SessionContext = createContext<string | null>(null)

export const SessionProvider = SessionContext.Provider

/** Read the current session id. Must be used within a SessionProvider. */
export function useSessionId(): string {
  const id = useContext(SessionContext)
  if (id === null) {
    throw new Error('useSessionId must be used within a SessionProvider')
  }
  return id
}
