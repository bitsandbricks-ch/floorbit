/** Alignment guides for seats placed freely (SeatHandles.tsx): while seats are dragged, a moving
 *  seat that comes within ``reach`` of another seat's column or row snaps onto it and a guide shows. */

export type Pt = [number, number]
/** A guide in the block's frame, in seats: a column (``x``) or a row (``y``) through seat centres. */
export type Guide = { x: number; from: number; to: number } | { y: number; from: number; to: number }

export const GUIDE_REACH = 0.25

/** The shift that lines the moving seats (already moved by ``by``) up with the others, and the guides. */
export function alignSeats(moving: Pt[], others: Pt[], by: Pt, reach = GUIDE_REACH): { by: Pt; guides: Guide[] } {
  const near = (axis: 0 | 1) => {
    let best: number | null = null
    for (const m of moving) {
      for (const o of others) {
        const d = o[axis] - (m[axis] + by[axis])
        if (Math.abs(d) <= reach && (best == null || Math.abs(d) < Math.abs(best))) best = d
      }
    }
    return best
  }
  const dx = near(0), dy = near(1)
  const out: Pt = [by[0] + (dx ?? 0), by[1] + (dy ?? 0)]
  const guides: Guide[] = []
  const placed = moving.map((m): Pt => [m[0] + out[0], m[1] + out[1]])
  const same = (a: number, b: number) => Math.abs(a - b) < 0.001
  // One guide per column or row the moving seats now share with others, across all the seats on it.
  for (const axis of [0, 1] as const) {
    if ((axis ? dy : dx) == null) continue
    const lines = new Set(placed.map((p) => p[axis]).filter((v) => others.some((o) => same(o[axis], v))))
    for (const v of lines) {
      const on = [...placed, ...others].filter((p) => same(p[axis], v)).map((p) => p[1 - axis])
      const span = { from: Math.min(...on) + 0.5, to: Math.max(...on) + 0.5 }
      guides.push(axis ? { y: v + 0.5, ...span } : { x: v + 0.5, ...span })
    }
  }
  return { by: out, guides }
}
