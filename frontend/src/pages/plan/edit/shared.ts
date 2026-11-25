import type { PlanMark, SeatViewData } from '@/api/types'
import type { ItemRef } from './geometry'
import { isLine } from '../lineMarks'

export const LAYER_IDS = ['overview', 'safety', 'network', 'electrical', 'services'] as const
export const ZONE_COLORS = ['muted', 'bit', 'trace', 'warn', 'down'] as const

/** The fields several selected items can be given at once. */
export type SharedField = 'layer' | 'style' | 'color' | 'size' | 'rotation' | 'tint'
type Edit = [ItemRef, Record<string, unknown>, Record<string, unknown>]

// What a field reads as when it's missing, so "missing" and the default count as the same value.
const DEFAULTS: Record<SharedField, unknown> = { layer: 'overview', style: 'solid', color: 'muted', size: 'm', rotation: 0, tint: null }
const HAS: Record<SharedField, (m: PlanMark) => boolean> = {
  layer: () => true,
  style: (m) => m.kind === 'wall',
  color: (m) => m.kind === 'zone',
  size: (m) => m.kind === 'text' || m.kind === 'icon',
  rotation: (m) => !isLine(m),
  tint: () => true,
}

function rowsOf(data: SeatViewData, items: ItemRef[]) {
  return items.map((r) => {
    if (r.kind === 'mark') {
      const m = data.drawing?.marks?.find((x) => x.id === r.id)
      return m ? { ref: r, mark: m, read: (f: SharedField) => (m as unknown as Record<string, unknown>)[f] ?? DEFAULTS[f] } : null
    }
    if (r.kind === 'block') {
      const s = data.drawing?.shapes.find((x) => x.id === r.id)
      return s ? { ref: r, mark: null, read: (f: SharedField) => (f === 'rotation' ? s.rotation : undefined) } : null
    }
    return null
  })
}

/** What a shared field reads as when the selected items differ. */
export const MIXED = Symbol('mixed')

/** For a selection of two or more, each field every item in it has, with its value when they all
 *  agree and MIXED when they differ. A field some item lacks (a wall's colour) is left out. */
export function sharedFields(data: SeatViewData, items: ItemRef[]): Partial<Record<SharedField, unknown>> {
  const rows = rowsOf(data, items)
  if (rows.length < 2 || rows.some((r) => !r)) return {}
  const out: Partial<Record<SharedField, unknown>> = {}
  for (const f of Object.keys(DEFAULTS) as SharedField[]) {
    const fits = rows.every((r) => (r!.mark ? HAS[f](r!.mark) : f === 'rotation'))
    if (!fits) continue
    const values = new Set(rows.map((r) => r!.read(f)))
    out[f] = values.size === 1 ? [...values][0] : MIXED
  }
  return out
}

/** What setting ``field`` to ``value`` on every item changes: [item, before, after] for each that
 *  isn't at that value already. Picking a size also drops a corner-handle stretch, as for one. */
export function sharedEdits(data: SeatViewData, items: ItemRef[], field: SharedField, value: unknown): Edit[] {
  const edits: Edit[] = []
  for (const row of rowsOf(data, items)) {
    if (!row) continue
    if (row.mark && !HAS[field](row.mark)) continue
    if (!row.mark && field !== 'rotation') continue
    const before = row.read(field)
    if (field === 'size') {
      const scale = row.mark?.scale ?? 1
      if (before !== value || scale !== 1) edits.push([row.ref, { size: before, scale }, { size: value, scale: 1 }])
    } else if (before !== value) {
      edits.push([row.ref, { [field]: before }, { [field]: value }])
    }
  }
  return edits
}
