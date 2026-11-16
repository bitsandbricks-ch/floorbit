import type { SeatViewData } from '@/api/types'
import { type ItemRef, allItems, outlineOf, sameRef } from './geometry'

/** The plan's items in reading order: by rows (one seat high) from the top, then left to right,
 *  so Tab goes through the plan the way the eye does. */
export function readingOrder(data: SeatViewData): ItemRef[] {
  const row = data.drawing?.cell ?? 32
  return allItems(data)
    .map((r) => ({ r, c: outlineOf(data, r)?.centre }))
    .filter((x): x is { r: ItemRef; c: { x: number; y: number } } => !!x.c)
    .sort((a, b) => Math.round(a.c.y / row) - Math.round(b.c.y / row) || a.c.x - b.c.x)
    .map((x) => x.r)
}

/** The item after (or, ``back``, before) ``from`` in reading order, wrapping around. */
export function nextItem(data: SeatViewData, from: ItemRef | null, back = false): ItemRef | null {
  const order = readingOrder(data)
  if (!order.length) return null
  const i = from ? order.findIndex((r) => sameRef(r, from)) : -1
  if (i < 0) return back ? order[order.length - 1] : order[0]
  return order[(i + (back ? order.length - 1 : 1)) % order.length]
}
