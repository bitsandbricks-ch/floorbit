/** Widget levels (issue #924): the same data drawn small (a number and a state), medium (a short
 *  list or a graph) or large (the details), picked from the size of the box it sits in. Any box
 *  size works; these are only where each kind starts to read well. */

export type Level = 's' | 'm' | 'l'
export type LevelPin = 'auto' | Level
export const LEVEL_PINS: LevelPin[] = ['auto', 's', 'm', 'l']

export type Kind = 'stat' | 'status' | 'graph' | 'table' | 'list' | 'gauge' | 'bar' | 'column' | 'histogram' | 'pie'
export type KindPick = 'auto' | Kind
export const KIND_PICKS: KindPick[] = ['auto', 'stat', 'gauge', 'status', 'list', 'table', 'bar', 'column', 'histogram', 'pie', 'graph']

/** Smallest box in px (width, height) for medium and for large. Roughly 3×2 and 6×3 cells on the
 *  12-column grid of a 1080p screen, the thresholds Mike agreed on. */
const FLOOR: Record<Kind, { m: [number, number]; l: [number, number] }> = {
  stat: { m: [240, 150], l: [480, 300] },
  status: { m: [220, 120], l: [460, 280] },
  list: { m: [220, 120], l: [460, 280] },
  graph: { m: [260, 130], l: [520, 280] },
  table: { m: [300, 150], l: [560, 280] },
  gauge: { m: [200, 150], l: [420, 300] },
  bar: { m: [240, 120], l: [480, 280] },
  column: { m: [240, 140], l: [480, 280] },
  histogram: { m: [240, 140], l: [480, 280] },
  pie: { m: [280, 160], l: [480, 300] },
}

/** The level for a box of ``w`` × ``h`` px, unless the pane pins one. */
export function pickLevel(kind: Kind, w: number, h: number, pin: LevelPin = 'auto'): Level {
  if (pin !== 'auto') return pin
  const f = FLOOR[kind]
  if (w >= f.l[0] && h >= f.l[1]) return 'l'
  if (w >= f.m[0] && h >= f.m[1]) return 'm'
  return 's'
}

/** One list or table row, in px: what "rows that fit" counts with. */
export const ROW_H = 28

/** Rows that fit ``h`` px after ``reserve`` px of head and footer, at least one. */
export const rowsThatFit = (h: number, reserve = 0) => Math.max(1, Math.floor((h - reserve) / ROW_H))
