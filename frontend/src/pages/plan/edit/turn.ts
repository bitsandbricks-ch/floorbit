import type { SeatViewData } from '@/api/types'
import type { ItemRef } from './geometry'

/** The rotation changes that turn ``refs`` a quarter turn each, in place (``back`` turns the other
 *  way): [item, before, after]. Only blocks, labels and icons turn; the rest is left out. */
export function quarterTurns(data: SeatViewData, refs: ItemRef[], back = false): [ItemRef, { rotation: number }, { rotation: number }][] {
  const out: [ItemRef, { rotation: number }, { rotation: number }][] = []
  for (const r of refs) {
    let now: number | undefined
    if (r.kind === 'block') { const b = data.drawing?.shapes.find((s) => s.id === r.id); if (b) now = b.rotation ?? 0 }
    if (r.kind === 'mark') {
      const m = data.drawing?.marks?.find((x) => x.id === r.id)
      if (m && (m.kind === 'text' || m.kind === 'icon')) now = m.rotation ?? 0
    }
    if (now == null) continue
    out.push([r, { rotation: now }, { rotation: (((now + (back ? -90 : 90)) % 360) + 360) % 360 }])
  }
  return out
}
