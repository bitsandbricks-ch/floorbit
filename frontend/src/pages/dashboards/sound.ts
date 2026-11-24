import { useCallback, useEffect, useRef, useState } from 'react'

/** The ids in ``now`` that weren't in ``seen``: what just went down with nobody on it. */
export function freshIds(seen: ReadonlySet<string>, now: readonly string[]): string[] {
  return now.filter((id) => !seen.has(id))
}

type Ctx = AudioContext

/** Two short rising notes, quiet enough for a NOC room: built here, so there is no file to ship. */
function chime(ctx: Ctx) {
  const start = ctx.currentTime + 0.02
  for (const [i, freq] of [660, 880].entries()) {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    const at = start + i * 0.22
    osc.type = 'sine'
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0.0001, at)
    gain.gain.exponentialRampToValueAtTime(0.25, at + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.2)
    osc.connect(gain).connect(ctx.destination)
    osc.start(at)
    osc.stop(at + 0.22)
  }
}

/** A wall's tone for new problems (#1137). ``ids`` are the problems down with nobody on them; each
 *  one sounds once, when it first shows. What is already down when the screen opens stays quiet,
 *  so a reload (a new version, the Wi-Fi) doesn't ring again. ``blocked``: the browser wants a
 *  click before it plays anything; ``allow`` is that click. */
export function useProblemSound(on: boolean, ids: string[] | undefined) {
  const ctx = useRef<Ctx | null>(null)
  const seen = useRef<Set<string> | null>(null)
  const [blocked, setBlocked] = useState(false)
  const key = ids?.join(',')

  useEffect(() => {
    if (!on) return undefined
    const Audio = window.AudioContext as typeof AudioContext | undefined
    if (!Audio) return undefined
    const made = new Audio()
    ctx.current = made
    const check = () => setBlocked(made.state === 'suspended')
    void made.resume().catch(() => {}).finally(check)
    made.addEventListener('statechange', check)
    return () => {
      made.removeEventListener('statechange', check)
      void made.close().catch(() => {})
      ctx.current = null
      setBlocked(false)
    }
  }, [on])

  useEffect(() => {
    if (!ids) return
    if (!seen.current) {   // the first answer: what is down already
      seen.current = new Set(ids)
      return
    }
    const fresh = freshIds(seen.current, ids)
    // Forget what was taken, so it rings again if it comes back.
    seen.current = new Set(ids)
    if (on && fresh.length && ctx.current?.state === 'running') chime(ctx.current)
    // ``key`` stands for ``ids``: a new array with the same problems is no change.
  }, [key, on]) // eslint-disable-line react-hooks/exhaustive-deps

  const allow = useCallback(() => { void ctx.current?.resume().catch(() => {}) }, [])
  return { blocked: on && blocked, allow }
}
