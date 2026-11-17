import type { SeatViewData } from '@/api/types'

export interface Place { kind: 'block' | 'switch'; name: string; at: { x: number; y: number } }

const norm = (s: string) => s.trim().toLowerCase().replace(/[\s_]+/g, '-')

/** A seat block or switch on this plan by its name, for the Find box: the exact name first,
 *  then a switch whose name starts with what was typed when only one does ("sw-c" for "sw-c-01"). */
export function findPlace(query: string, data: Pick<SeatViewData, 'drawing' | 'switches'>): Place | null {
  const q = norm(query)
  if (!q) return null
  const block = data.drawing?.shapes.find((b) => b.name && norm(b.name) === q)
  if (block) return { kind: 'block', name: block.name, at: { x: block.cx, y: block.cy } }
  const sw = data.switches.find((w) => norm(w.name) === q)
  if (sw) return { kind: 'switch', name: sw.name, at: { x: sw.x, y: sw.y } }
  const starts = data.switches.filter((w) => norm(w.name).startsWith(q))
  if (q.length >= 3 && starts.length === 1) return { kind: 'switch', name: starts[0].name, at: { x: starts[0].x, y: starts[0].y } }
  return null
}
