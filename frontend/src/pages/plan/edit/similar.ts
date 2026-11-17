import type { SeatViewData } from '@/api/types'
import type { ItemRef } from './geometry'

/** Every item like the ones in ``refs``: the same kind, and for drawn marks the same sort (walls
 *  pick walls, text picks text). ``items`` is what can be picked (the plan's items and cables). */
export function similar(data: SeatViewData, items: ItemRef[], refs: ItemRef[]): ItemRef[] {
  const marks = data.drawing?.marks ?? []
  const sortOf = (id: string) => marks.find((m) => m.id === id)?.kind
  const kinds = new Set(refs.filter((r) => r.kind !== 'mark').map((r) => r.kind))
  const sorts = new Set(refs.filter((r) => r.kind === 'mark').map((r) => sortOf(r.id)).filter(Boolean))
  return items.filter((r) => (r.kind === 'mark' ? sorts.has(sortOf(r.id)) : kinds.has(r.kind)))
}
