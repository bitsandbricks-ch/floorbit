import type { PlanShape } from '@/api/types'

/** What to call a block in lists and the panel title: its name, or for a block without one its
 *  first and last seat ("A-1 – B-12"), so unnamed blocks still tell apart (Mike: the item list
 *  showed only "Seat block —"). */
export function blockName(shape: Pick<PlanShape, 'name' | 'cells'> | undefined): string {
  if (!shape) return '—'
  if (shape.name?.trim()) return shape.name.trim()
  const seats = shape.cells.map((c) => c.seat).filter(Boolean)
  if (!seats.length) return '—'
  return seats.length === 1 ? seats[0] : `${seats[0]} – ${seats[seats.length - 1]}`
}
