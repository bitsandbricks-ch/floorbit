/** Gaps inside a seat block (floorbit/seat_gaps.py): ``after`` a column or row counted from the
 *  block's top left as drawn, ``size`` in seats. */
export interface Gap { after: number; size: number }

export const GAP_MIN = 0.25, GAP_MAX = 20

/** Gaps as the server keeps them (floorbit/seat_gaps.py): one per place, inside the block, sorted. */
export function cleanGaps(list: Gap[], count: number): Gap[] {
  const merged = new Map<number, number>()
  for (const g of list) {
    const after = Math.round(Number(g.after)), size = Math.min(GAP_MAX, Math.max(GAP_MIN, Number(g.size) || 1))
    if (after >= 1 && after < count) merged.set(after, Math.round(size * 100) / 100)
  }
  return [...merged.entries()].sort((a, b) => a[0] - b[0]).map(([after, size]) => ({ after, size }))
}

/** Where a new gap goes: the middle first, then the nearest free place; null when every place has one. */
export function freeGapSpot(gaps: Gap[], count: number): number | null {
  const taken = new Set(gaps.map((g) => g.after))
  const mid = Math.max(1, Math.floor(count / 2))
  const spots = Array.from({ length: Math.max(0, count - 1) }, (_, i) => i + 1).sort((a, b) => Math.abs(a - mid) - Math.abs(b - mid))
  return spots.find((n) => !taken.has(n)) ?? null
}

