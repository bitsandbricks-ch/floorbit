import type { PlanBlock, PlanShape } from '@/api/types'

/** Each shape's counts. Matched by id, else by position (the server sends them in shape order),
 *  never by name: blocks without a name, or with the same one, would all get the first block's. */
export function blockSums(shapes: PlanShape[], sums: PlanBlock[]): (PlanBlock | undefined)[] {
  const byId = new Map(sums.filter((b) => b.id).map((b) => [b.id!, b]))
  return shapes.map((s, i) => (s.id && byId.has(s.id) ? byId.get(s.id) : sums.length === shapes.length ? sums[i] : undefined))
}

/** What a block is called on the plan: its name, else its rows ("A–D"), else its first seat. */
export function shapeLabel(b: Pick<PlanShape, 'name' | 'rows' | 'cells'>): string {
  if (b.name) return b.name
  const letters = [...new Set((b.rows ?? []).map((r) => r.text).filter(Boolean))]
  if (letters.length) return letters.length > 1 ? `${letters[0]}–${letters[letters.length - 1]}` : letters[0]
  return b.cells[0]?.seat ?? ''
}

/** Left, top, right, bottom. */
export type Rect = [number, number, number, number]

/** A turned block's outline as an upright box, with the outline's 6 units of padding. */
export function shapeRect(b: Pick<PlanShape, 'cx' | 'cy' | 'w' | 'h' | 'rotation'>): Rect {
  const r = (b.rotation * Math.PI) / 180
  const hw = Math.abs((b.w / 2) * Math.cos(r)) + Math.abs((b.h / 2) * Math.sin(r)) + 6
  const hh = Math.abs((b.w / 2) * Math.sin(r)) + Math.abs((b.h / 2) * Math.cos(r)) + 6
  return [b.cx - hw, b.cy - hh, b.cx + hw, b.cy + hh]
}

/** A rough width of a text line at ``size``: the plan's sans at about 0.6 em a character. */
export const textWidth = (text: string, size: number) => text.length * size * 0.6
