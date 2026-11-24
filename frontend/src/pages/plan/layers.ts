/** The Seats view's layers: the seats are always there, everything else stacks on top and can be
 *  switched off or faded. The choice lives in the URL (``?layers=…&fade=…``) so a link or a big
 *  screen shows the same thing. */

export const LAYERS = ['grid', 'marks', 'network', 'electrical', 'status', 'problems', 'firewalls', 'wifi', 'safety', 'crew', 'checkin', 'services'] as const
export type LayerId = (typeof LAYERS)[number]

export const PRESETS = {
  overview: ['marks', 'checkin'],
  network: ['marks', 'network', 'wifi'],
  electrical: ['marks', 'electrical'],
  ops: ['marks', 'network', 'status', 'problems', 'firewalls', 'crew', 'checkin'],
} satisfies Record<string, LayerId[]>
export type PresetId = keyof typeof PRESETS
/** Keys 1 to 4 pick these presets in Live mode, in the order the layer panel lists them. */
export const PRESET_KEYS = Object.keys(PRESETS) as PresetId[]

/** What the page showed before it had layers (switches and uplinks, labels, check-in corners), on the
 *  editor's grid. */
export const DEFAULT_LAYERS: LayerId[] = ['grid', 'marks', 'network', 'checkin']

/** The grid is a backdrop, not part of a preset: presets leave it as it is. */
const BACKDROP: LayerId[] = ['grid']

/** The layer a mark belongs to (floorbit/plan_marks.py LAYERS) to the layer that shows it. */
export const MARK_LAYER: Record<string, LayerId> = {
  overview: 'marks', safety: 'safety', network: 'network', electrical: 'electrical', services: 'services',
}

export interface LayerState {
  on: ReadonlySet<LayerId>
  /** 0.1 to 1, only for layers not at full strength. */
  fade: Partial<Record<LayerId, number>>
}

const isLayer = (v: string): v is LayerId => (LAYERS as readonly string[]).includes(v)

export function readLayers(params: URLSearchParams): LayerState {
  const raw = params.get('layers')
  let on: LayerId[]
  if (raw !== null) {
    on = raw.split(',').filter(isLayer)
  } else {
    // Links from before the layers: ?traffic=1, ?power=1, ?firewalls=1.
    on = [...DEFAULT_LAYERS]
    if (params.get('traffic') === '1') on.push('status')
    if (params.get('power') === '1') on.push('electrical')
    if (params.get('firewalls') === '1') on.push('firewalls')
  }
  const fade: LayerState['fade'] = {}
  for (const part of (params.get('fade') ?? '').split(',')) {
    const [id, pct] = part.split(':')
    const n = Number(pct)
    if (isLayer(id) && Number.isFinite(n) && n >= 10 && n < 100) fade[id] = Math.round(n) / 100
  }
  return { on: new Set(on), fade }
}

/** ``params`` with the layers written in; the old one-layer switches are dropped. */
export function writeLayers(params: URLSearchParams, state: LayerState): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const k of ['traffic', 'power', 'firewalls', 'layers', 'fade']) next.delete(k)
  const on = LAYERS.filter((l) => state.on.has(l))
  if (!same(on, DEFAULT_LAYERS)) next.set('layers', on.join(','))
  const fade = LAYERS.filter((l) => state.fade[l] !== undefined).map((l) => `${l}:${Math.round(state.fade[l]! * 100)}`)
  if (fade.length) next.set('fade', fade.join(','))
  return next
}

export function presetOf(on: ReadonlySet<LayerId>): PresetId | null {
  const list = LAYERS.filter((l) => on.has(l) && !BACKDROP.includes(l))
  return (Object.keys(PRESETS) as PresetId[]).find((p) => same(list, LAYERS.filter((l) => (PRESETS[p] as LayerId[]).includes(l)))) ?? null
}

/** ``state`` switched to a preset, keeping the grid as it was. */
export function applyPreset(state: LayerState, preset: PresetId): LayerState {
  return { on: new Set([...PRESETS[preset], ...BACKDROP.filter((l) => state.on.has(l))]), fade: state.fade }
}

export const opacity = (state: LayerState, id: LayerId) => state.fade[id] ?? 1

/** The CSS variables the plan's stylesheet reads for layers drawn inside the seats (rings, corners, fills). */
export function layerStyle(state: LayerState): React.CSSProperties {
  const style: Record<string, number> = {}
  for (const id of LAYERS) style[`--op-${id}`] = opacity(state, id)
  return style as React.CSSProperties
}

function same(a: readonly string[], b: readonly string[]) {
  const sa = [...a].sort(), sb = [...b].sort()
  return sa.length === sb.length && sa.every((v, i) => v === sb[i])
}
