import type { PlanView, PlanViewFields } from '@/api/planViews'
import type { View } from '../model'

/** The address param that opens a saved view (and says which one is open). */
export const VIEW_PARAM = 'pv'

/** The plan's address switched to ``v``: its hall, layers and filter, and ``pv`` so the plan moves
 *  to its part of the hall once it has loaded. Everything else (an open seat, editing) stays. */
export function applyView(params: URLSearchParams, v: PlanView): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const k of ['layers', 'fade', 'show', 'traffic', 'power', 'firewalls', 'seat', 'block', 'switch']) next.delete(k)
  next.set('hall', v.hall)
  if (v.layers !== undefined) next.set('layers', v.layers)
  if (v.fade) next.set('fade', v.fade)
  if (v.show !== 'all') next.set('show', v.show)
  next.set(VIEW_PARAM, v.id)
  return next
}

/** What the plan shows now, as the fields of a view to save. */
export function currentView(params: URLSearchParams, hall: string, view: View, name: string, priv: boolean): PlanViewFields {
  const layers = params.get('layers')
  const show = (params.get('show') ?? 'all') as PlanView['show']
  const round = (n: number) => Math.round(n * 100) / 100
  return {
    name, hall, show, private: priv,
    view: { x: round(view.x), y: round(view.y), w: round(view.w), h: round(view.h) },
    ...(layers !== null ? { layers } : {}),
    ...(params.get('fade') ? { fade: params.get('fade')! } : {}),
  }
}
