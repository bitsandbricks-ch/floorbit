// Whether Floorbit's database answers, for the banner (components/DatabaseBanner.tsx).
import { useEffect, useRef, useState } from 'react'

/** Fired by the API client when a request came back "database unavailable", so the banner
 *  shows at once instead of at the next check. */
export const DB_DOWN_EVENT = 'floorbit:database-down'

type Health = { database?: 'up' | 'down'; down_for?: number }

const EVERY_UP = 30_000
const EVERY_DOWN = 5_000

/** Whether the database answers, from /healthz (open, cheap): every 30 s, every 5 s while it
 *  doesn't. When the server itself can't be reached it says nothing: that's not this banner. */
export function useDatabaseDown(): { down: boolean; downFor: number; back: boolean } {
  const [state, setState] = useState({ down: false, downFor: 0, back: false })
  const wasDown = useRef(false)
  useEffect(() => {
    let stop = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const check = () => {
      clearTimeout(timer)
      fetch('/healthz', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then((r) => r.json() as Promise<Health>)
        .then((h) => {
          if (stop) return
          const down = h.database === 'down'
          const back = wasDown.current && !down
          wasDown.current = down
          setState((s) => ({ down, downFor: h.down_for ?? 0, back: back || (s.back && !down) }))
        })
        .catch(() => { /* the server itself is away: not the database's banner */ })
        .finally(() => { if (!stop) timer = setTimeout(check, wasDown.current ? EVERY_DOWN : EVERY_UP) })
    }
    check()
    window.addEventListener(DB_DOWN_EVENT, check)
    return () => { stop = true; clearTimeout(timer); window.removeEventListener(DB_DOWN_EVENT, check) }
  }, [])
  // "Back" shows for a few seconds, then goes.
  useEffect(() => {
    if (!state.back) return
    const t = setTimeout(() => setState((s) => ({ ...s, back: false })), 6_000)
    return () => clearTimeout(t)
  }, [state.back])
  return state
}
