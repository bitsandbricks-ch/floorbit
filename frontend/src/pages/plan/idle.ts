import { useEffect, useState } from 'react'

/** True once nobody has moved the pointer, touched or typed for ``ms``: a wall screen hides the
 *  cursor and the zoom buttons then, and shows them again with the next move. */
export function useIdle(ms: number, on = true) {
  const [idle, setIdle] = useState(false)
  useEffect(() => {
    if (!on) return
    let timer = window.setTimeout(() => setIdle(true), ms)
    const wake = () => {
      window.clearTimeout(timer)
      setIdle(false)
      timer = window.setTimeout(() => setIdle(true), ms)
    }
    const events = ['pointermove', 'pointerdown', 'keydown', 'wheel'] as const
    for (const e of events) window.addEventListener(e, wake, { passive: true })
    return () => {
      window.clearTimeout(timer)
      for (const e of events) window.removeEventListener(e, wake)
    }
  }, [ms, on])
  return on && idle
}
