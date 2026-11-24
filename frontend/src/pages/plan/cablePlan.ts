import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { CablePlan } from '@/api/types'

/** The cables to draw in a hall (GET /api/cable-plan), kept fresh while ``enabled``: positions
 *  follow blocks and switches, so a moved block or a new cable asks again. */
export function useCablePlan(hall: string | undefined, enabled: boolean) {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: qk.cablePlan(hall ?? ''),
    queryFn: () => get<CablePlan>(`/api/cable-plan${hall ? `?hall=${encodeURIComponent(hall)}` : ''}`),
    enabled: enabled && !!hall,
    staleTime: 15_000,
  })
  // One edit sends a burst of live events (one per saved item, plan and cables both): read the
  // cables once for the burst, and let a read already on its way answer it (#1301).
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])
  const again = () => {
    if (!enabled) return
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      timer.current = null
      void qc.invalidateQueries({ queryKey: qk.cablePlan(hall ?? '') }, { cancelRefetch: false })
    }, 200)
  }
  useLiveEvent('cables.changed', again)
  useLiveEvent('plan.changed', again)
  return enabled ? q.data : undefined
}

/** A cable's points (% of the plan) as an SVG path in drawing units, with round corners when asked. */
export function cablePath(points: [number, number][], size: { w: number; h: number }, corners: 'square' | 'round' | 'straight' = 'square') {
  const pts = points.map(([x, y]) => [(x / 100) * size.w, (y / 100) * size.h])
  if (pts.length < 2) return ''
  const f = (n: number) => n.toFixed(1)
  const d = [`M${f(pts[0][0])} ${f(pts[0][1])}`]
  for (let i = 1; i < pts.length; i++) {
    const [x, y] = pts[i]
    if (corners !== 'round' || i === pts.length - 1) { d.push(`L${f(x)} ${f(y)}`); continue }
    // Stop short of the bend, curve through it, carry on (as the classic editor draws them).
    const [px, py] = pts[i - 1], [nx, ny] = pts[i + 1]
    const lin = Math.hypot(x - px, y - py), lout = Math.hypot(nx - x, ny - y)
    const r = Math.min(12, lin / 2, lout / 2)
    if (!r) { d.push(`L${f(x)} ${f(y)}`); continue }
    const ax = x - ((x - px) / lin) * r, ay = y - ((y - py) / lin) * r
    const bx = x + ((nx - x) / lout) * r, by = y + ((ny - y) / lout) * r
    d.push(`L${f(ax)} ${f(ay)} Q${f(x)} ${f(y)} ${f(bx)} ${f(by)}`)
  }
  return d.join(' ')
}
