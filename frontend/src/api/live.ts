import { useCallback, useEffect, useRef } from 'react'
import { queryClient } from '../queryClient'

// One EventSource for the whole page, shared by every hook: browsers allow only six connections
// per host, and a page with a stream per hook ran out of them, so its other requests stalled.
// Hooks register here rather than on the EventSource, so a new one (see `reopenLater`) serves them too.
type Listener = (e: MessageEvent) => void
const listeners = new Map<string, Set<Listener>>()
let shared: { source: EventSource; users: number; retry?: ReturnType<typeof setTimeout> } | null = null

// The browser gives up on a stream the server refused (it answers 503 when too many pages are open,
// integrations/events.py): ask again a little later, spread out so they don't all come back at once.
const RETRY_MIN_MS = 20_000
const RETRY_SPREAD_MS = 20_000

function dispatch(type: string) {
  return (e: Event) => listeners.get(type)?.forEach((fn) => fn(e as MessageEvent))
}

function open(): EventSource {
  const source = new EventSource('/api/events')
  // While the stream was down (Wi-Fi blip, pod restart) or the server dropped events for us,
  // changes went by unseen: fetch everything again instead of showing a stale board.
  let dropped = false
  const refetch = () => void queryClient.invalidateQueries()
  source.addEventListener('error', () => {
    dropped = true
    if (source.readyState === 2) reopenLater(source)    // CLOSED: the browser won't try again
  })
  source.addEventListener('hello', () => {
    if (dropped) refetch()
    dropped = false
  })
  source.addEventListener('resync', refetch)
  for (const type of listeners.keys()) source.addEventListener(type, dispatch(type))
  return source
}

function reopenLater(source: EventSource) {
  if (!shared || shared.source !== source || shared.retry) return
  shared.retry = setTimeout(() => {
    if (!shared || shared.source !== source) return
    shared.retry = undefined
    shared.source = open()
  }, RETRY_MIN_MS + Math.random() * RETRY_SPREAD_MS)
}

function listen(type: string, fn: Listener) {
  let set = listeners.get(type)
  if (!set) {
    set = new Set()
    listeners.set(type, set)
    shared?.source.addEventListener(type, dispatch(type))
  }
  set.add(fn)
}

function acquire() {
  if (!shared) shared = { source: open(), users: 0 }
  shared.users++
}

function release() {
  if (!shared || --shared.users > 0) return
  shared.source.close()
  if (shared.retry) clearTimeout(shared.retry)
  shared = null
  listeners.clear()
}

/** Calls `onEvent` for each live event of this type from /api/events (Server-Sent Events). */
export function useLiveEvent(type: string, onEvent: (data: unknown) => void) {
  const handler = useRef(onEvent)
  useEffect(() => {
    handler.current = onEvent
  }, [onEvent])
  const one = useCallback((data: unknown) => handler.current(data), [])
  useLiveEvents(type, one)
}

/** `useLiveEvent` for several types at once: `types` is one name or several, joined by spaces. */
export function useLiveEvents(types: string, onEvent: (data: unknown, type: string) => void) {
  const handler = useRef(onEvent)
  useEffect(() => {
    handler.current = onEvent
  }, [onEvent])
  useEffect(() => {
    if (typeof EventSource === 'undefined') return
    const wanted = types.split(' ').filter(Boolean)
    const fn: Listener = (e) => {
      try {
        const event = JSON.parse(e.data) as { type?: string; data?: unknown }
        if (event.type && wanted.includes(event.type)) handler.current(event.data, event.type)   // events are named by type
      } catch {
        // not one of ours
      }
    }
    acquire()
    for (const type of wanted) listen(type, fn)
    return () => {
      for (const type of wanted) listeners.get(type)?.delete(fn)
      release()
    }
  }, [types])
}
