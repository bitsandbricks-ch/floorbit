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

export interface LabelBox {
  /** Centre x, top y, width and height, in drawing units. */
  x: number
  y: number
  w: number
  h: number
}

/** Where each label goes so none lands on another label or on a block it doesn't belong to.
 *  Each item offers places in order of preference (above its block, then beside it); the highest
 *  rank picks first, then top to bottom. An item with no free place is left out. ``obstacles`` are
 *  the blocks' outlines; item i may cover obstacle i (its own block). Returns item -> place index. */
/** ``rank``: higher picks first, so a block with problems keeps its label over a quiet neighbour. */
export function placeLabels(items: { places: LabelBox[]; rank: number }[], obstacles: Rect[] = []): Map<number, number> {
  const top = (i: number) => items[i].places[0]?.y ?? 0
  const order = items.map((_, i) => i).sort((a, b) => items[b].rank - items[a].rank || top(a) - top(b))
  const kept: Rect[] = []
  const out = new Map<number, number>()
  for (const i of order) {
    const at = items[i].places.findIndex((p) => {
      const r = toRect(p)
      return !kept.some((k) => overlaps(k, r)) && !obstacles.some((o, j) => j !== i && overlaps(o, r))
    })
    if (at < 0) continue
    kept.push(toRect(items[i].places[at]))
    out.set(i, at)
  }
  return out
}

/** Left, top, right, bottom. */
export type Rect = [number, number, number, number]
const toRect = (b: LabelBox): Rect => [b.x - b.w / 2, b.y, b.x + b.w / 2, b.y + b.h]
const overlaps = (a: Rect, b: Rect) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]

/** A turned block's outline as an upright box, with the outline's 6 units of padding. */
export function shapeRect(b: Pick<PlanShape, 'cx' | 'cy' | 'w' | 'h' | 'rotation'>): Rect {
  const r = (b.rotation * Math.PI) / 180
  const hw = Math.abs((b.w / 2) * Math.cos(r)) + Math.abs((b.h / 2) * Math.sin(r)) + 6
  const hh = Math.abs((b.w / 2) * Math.sin(r)) + Math.abs((b.h / 2) * Math.cos(r)) + 6
  return [b.cx - hw, b.cy - hh, b.cx + hw, b.cy + hh]
}

/** The places a label of ``w`` x ``h`` can go around a block: above it, then left, then right. */
export function placesAround(rect: Rect, w: number, h: number, gap: number): LabelBox[] {
  const midY = (rect[1] + rect[3]) / 2 - h / 2
  return [
    { x: (rect[0] + rect[2]) / 2, y: rect[1] - gap - h, w, h },
    { x: rect[0] - gap - w / 2, y: midY, w, h },
    { x: rect[2] + gap + w / 2, y: midY, w, h },
  ]
}

/** A rough width of a text line at ``size``: the plan's sans at about 0.6 em a character. */
export const textWidth = (text: string, size: number) => text.length * size * 0.6
