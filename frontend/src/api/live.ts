import { useEffect, useRef } from 'react'

// One EventSource for the whole page, shared by every hook: browsers allow only six connections
// per host, and a page with a stream per hook ran out of them, so its other requests stalled.
let shared: { source: EventSource; users: number } | null = null

function acquire(): EventSource {
  if (!shared) shared = { source: new EventSource('/api/events'), users: 0 }
  shared.users++
  return shared.source
}

function release(source: EventSource) {
  if (!shared || shared.source !== source) return
  if (--shared.users <= 0) {
    source.close()
    shared = null
  }
}

/** Calls `onEvent` for each live event of this type from /api/events (Server-Sent Events). */
export function useLiveEvent(type: string, onEvent: (data: unknown) => void) {
  const handler = useRef(onEvent)
  useEffect(() => {
    handler.current = onEvent
  }, [onEvent])
  useEffect(() => {
    if (typeof EventSource === 'undefined') return
    const source = acquire()
    const listen = (e: MessageEvent) => {
      try {
        const event = JSON.parse(e.data) as { type?: string; data?: unknown }
        if (event.type === type) handler.current(event.data)   // events are named by type
      } catch {
        // not one of ours
      }
    }
    source.addEventListener(type, listen as EventListener)
    return () => {
      source.removeEventListener(type, listen as EventListener)
      release(source)
    }
  }, [type])
}
