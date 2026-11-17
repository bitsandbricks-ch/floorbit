import type { SeatViewData } from '@/api/types'
import type { ItemRef } from './geometry'

/** The rotation changes that turn ``refs`` a quarter turn each, in place (``back`` turns the other
 *  way): [item, before, after]. Only blocks, labels, icons and zones turn; the rest is left out. */
export function quarterTurns(data: SeatViewData, refs: ItemRef[], back = false): [ItemRef, { rotation: number }, { rotation: number }][] {
  const out: [ItemRef, { rotation: number }, { rotation: number }][] = []
  for (const r of refs) {
    let now: number | undefined
    if (r.kind === 'block') { const b = data.drawing?.shapes.find((s) => s.id === r.id); if (b) now = b.rotation ?? 0 }
    if (r.kind === 'mark') {
      const m = data.drawing?.marks?.find((x) => x.id === r.id)
      if (m && (m.kind === 'text' || m.kind === 'icon' || m.kind === 'zone')) now = m.rotation ?? 0
    }
    if (now == null) continue
    out.push([r, { rotation: now }, { rotation: (((now + (back ? -90 : 90)) % 360) + 360) % 360 }])
  }
  return out
}

/** Whether ``ref`` can turn (and so gets a rotate handle). */
export function canTurnOne(data: SeatViewData, ref: ItemRef): boolean {
  return quarterTurns(data, [ref]).length > 0
}

/** The angle the rotate handle points at from ``centre``, in whole degrees clockwise from up (the
 *  handle sits above an unturned item), in 15° steps with ``steps``. */
export function angleTo(centre: { x: number; y: number }, p: { x: number; y: number }, steps: boolean): number {
  const raw = (Math.atan2(p.y - centre.y, p.x - centre.x) * 180) / Math.PI + 90
  const deg = steps ? Math.round(raw / 15) * 15 : Math.round(raw)
  return ((deg % 360) + 360) % 360
}
