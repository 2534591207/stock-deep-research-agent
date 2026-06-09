// Client-generated session id: one per browser tab, created lazily once.
// Not persisted across sessions — a page refresh starts a fresh conversation,
// matching the backend's in-memory per-session memory boundary.

let cachedSessionId: string | null = null

function generateId(): string {
  // Prefer the platform UUID generator; fall back to a simple random string
  // when it is unavailable (e.g. non-secure contexts).
  const c =
    typeof globalThis !== 'undefined'
      ? (globalThis.crypto as Crypto | undefined)
      : undefined
  if (c && typeof c.randomUUID === 'function') {
    return c.randomUUID()
  }
  const rand = () => Math.random().toString(36).slice(2)
  return `sid-${Date.now().toString(36)}-${rand()}${rand()}`
}

/** Return the stable session id for this tab, creating it on first call. */
export function getSessionId(): string {
  if (cachedSessionId === null) {
    cachedSessionId = generateId()
  }
  return cachedSessionId
}
