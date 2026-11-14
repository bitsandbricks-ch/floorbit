import { useEffect, useRef } from 'react'

/** Calls `onEvent` for each live event of this type from /api/events (Server-Sent Events). */
export function useLiveEvent(type: string, onEvent: (data: unknown) => void) {
  const handler = useRef(onEvent)
  useEffect(() => {
    handler.current = onEvent
  }, [onEvent])
  useEffect(() => {
    if (typeof EventSource === 'undefined') return
    const source = new EventSource('/api/events')
    const listen = (e: MessageEvent) => {
      try {
        const event = JSON.parse(e.data) as { type?: string; data?: unknown }
        if (event.type === type) handler.current(event.data)   // events are named by type
      } catch {
        // not one of ours
      }
    }
    source.addEventListener(type, listen as EventListener)
    return () => source.close()
  }, [type])
}
