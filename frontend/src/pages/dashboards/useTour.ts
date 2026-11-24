import { useEffect, useRef, useState } from 'react'
import { freshProblems } from './tour'

/** Where a tour is: stop ``i``, or the rows around a problem ``seat`` put in before the next stop.
 *  ``n`` counts the steps, so the progress bar starts over on each one. */
export interface TourStep { i: number; seat: string | null; n: number }

/** Steps through ``count`` stops, ``secs`` each, while not ``paused``. ``follow``: a seat that gets a
 *  problem is the next stop. ``stay``: the spotlight keeps to the newest problem while it lasts. */
export function useTour(count: number, secs: number, paused: boolean, problems: ReadonlySet<string> | null,
  follow: boolean, stay: boolean): TourStep {
  const [step, setStep] = useState<TourStep>({ i: 0, seat: null, n: 0 })
  const before = useRef<ReadonlySet<string> | null>(null)
  const queued = useRef<string | null>(null)
  const now = useRef(problems)
  useEffect(() => {
    now.current = problems
    if (!problems) return
    const fresh = freshProblems(before.current, problems)
    if (follow && fresh.length) queued.current = fresh[fresh.length - 1]
    before.current = problems
  }, [problems, follow])
  useEffect(() => {
    if (paused || count < 1) return
    const timer = window.setTimeout(() => setStep((s) => {
      const seat = queued.current
      queued.current = null
      if (seat && now.current?.has(seat)) return { i: s.i, seat, n: s.n + 1 }
      // The spotlight stays on a problem until it clears or a newer one comes.
      if (stay && s.seat && now.current?.has(s.seat)) return { ...s, n: s.n + 1 }
      return { i: s.seat && stay ? s.i : (s.i + 1) % count, seat: null, n: s.n + 1 }
    }), secs * 1000)
    return () => window.clearTimeout(timer)
  }, [step.n, paused, count, secs, stay])
  return count ? { ...step, i: step.i % count } : step
}
