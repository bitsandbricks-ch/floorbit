import { type LayerId, type LayerState, writeLayers } from './layers'

/** The plan workspace's modes: one canvas, different layers and tools. Live, Check-in and Network
 *  are layer presets of the same view; Kiosk is the same view without chrome; Edit adds the editor's
 *  selection and tools (pages/plan/edit/), crew with floorplan.edit only. The mode lives in the address (``?mode=``). */
export const MODES = ['live', 'checkin', 'network', 'edit'] as const
export type Mode = (typeof MODES)[number]

export const MODE_LAYERS: Record<Mode, LayerId[]> = {
  live: ['grid', 'marks', 'network', 'status', 'crew', 'checkin'],
  checkin: ['grid', 'marks', 'checkin'],
  network: ['grid', 'marks', 'network', 'status', 'firewalls', 'wifi'],
  edit: ['grid', 'marks', 'network', 'electrical', 'safety', 'services'],
}

export const readMode = (params: URLSearchParams): Mode => {
  const m = params.get('mode')
  return (MODES as readonly string[]).includes(m ?? '') ? (m as Mode) : 'live'
}

/** ``params`` switched to ``mode``: its layers, and the filter that fits it. */
export function switchMode(params: URLSearchParams, mode: Mode, state: LayerState): URLSearchParams {
  const next = writeLayers(params, { on: new Set(MODE_LAYERS[mode]), fade: state.fade })
  if (mode === 'live') next.delete('mode')
  else next.set('mode', mode)
  // Edit has its own selection; the seat, block and switch panels belong to the other modes.
  if (mode === 'edit') for (const k of ['seat', 'block', 'switch', 'view']) next.delete(k)
  if (mode === 'checkin') next.set('show', 'checked_in')
  else if (next.get('show') === 'checked_in') next.delete('show')
  return next
}

export const kioskHref = (hall: string, params: URLSearchParams) => {
  const next = new URLSearchParams()
  next.set('screen', '1')
  if (hall) next.set('hall', hall)
  for (const k of ['layers', 'fade', 'show']) { const v = params.get(k); if (v) next.set(k, v) }
  return `/plan?${next.toString()}`
}
