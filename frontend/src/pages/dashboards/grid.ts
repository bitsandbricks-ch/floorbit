import { type Node, isPane, planPane } from './model'

/** The grid a dashboard's panels sit on (floorbit/dashboards.py COLS), and how panels move on it
 *  without overlapping: like Kibana, everything floats up as far as it can. */

export const COLS = 24
export const MAX_PANELS = 24
export const MAX_SECTIONS = 12
/** Row height when the dashboard scrolls (``fit`` off), in pixels. */
export const ROW_PX = 40

/** On a Page, panel heights (rows) snap to where a widget reads small, medium and large (#923):
 *  with the pane's title, 3 rows draw a number, 5 a short list or a graph, 8 the details. Above
 *  large any height goes. */
export const PAGE_HEIGHTS = [3, 5, 8]
const TOP = PAGE_HEIGHTS[PAGE_HEIGHTS.length - 1]

/** The page height nearest ``h`` (a tie goes up). */
export function snapHeight(h: number): number {
  if (h >= TOP) return h
  return PAGE_HEIGHTS.reduce((best, x) => (Math.abs(x - h) <= Math.abs(best - h) ? x : best))
}

/** One step up (``dir`` 1) or down (-1) from ``h``: the next page height, a row at a time above large. */
export function stepHeight(h: number, dir: 1 | -1): number {
  if (dir > 0) return h >= TOP ? h + 1 : PAGE_HEIGHTS.find((x) => x > h) ?? TOP
  if (h > TOP) return h - 1
  return [...PAGE_HEIGHTS].reverse().find((x) => x < h) ?? PAGE_HEIGHTS[0]
}

export interface Panel { x: number; y: number; w: number; h: number; node: Node }
export interface Section { title?: string; folded?: boolean; panels: Panel[] }
type Box = Pick<Panel, 'x' | 'y' | 'w' | 'h'>

export const overlap = (a: Box, b: Box) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

/** Rows the panels take, down to the lowest one. */
export const rows = (panels: Box[]) => panels.reduce((n, p) => Math.max(n, p.y + p.h), 0)

const clampBox = <T extends Box>(p: T): T => {
  const w = Math.min(COLS, Math.max(1, Math.round(p.w)))
  const h = Math.min(60, Math.max(1, Math.round(p.h)))
  const x = Math.min(COLS - w, Math.max(0, Math.round(p.x)))
  return { ...p, x, w, h, y: Math.max(0, Math.round(p.y)) }
}

/** Every panel as high up as it goes without overlapping one above it. ``first`` (an index) wins
 *  a tie, so the panel being dragged takes the spot and the others make room. Keeps the order. */
export function compact<T extends Box>(panels: T[], first?: number): T[] {
  const order = panels.map((_, i) => i).sort((a, b) =>
    panels[a].y - panels[b].y || (a === first ? -1 : b === first ? 1 : 0) || panels[a].x - panels[b].x)
  const placed: T[] = []
  const out = [...panels]
  for (const i of order) {
    let p = clampBox(panels[i])
    // Pushed below anything it lands on, then floated up while nothing is in the way.
    for (let hit = placed.find((q) => overlap(p, q)); hit; hit = placed.find((q) => overlap(p, q))) p = { ...p, y: hit.y + hit.h }
    while (p.y > 0 && !placed.some((q) => overlap({ ...p, y: p.y - 1 }, q))) p = { ...p, y: p.y - 1 }
    placed.push(p)
    out[i] = p
  }
  return out
}

/** Panel ``i`` moved or resized to ``box``, the others making room. A panel it lands on goes below it
 *  once its top is above that panel's middle, else stays above it: the same in both directions. */
export function place<T extends Box>(panels: T[], i: number, box: Partial<Box>): T[] {
  const next = panels.map((p, j) => (j === i ? clampBox({ ...p, ...box }) : p))
  // First under every panel it lands on past the middle, then the rest make room below it.
  for (let below = true; below;) {
    const m = next[i]
    const hit = next.find((p, j) => j !== i && overlap(p, m) && m.y > p.y + p.h / 2)
    below = !!hit
    if (hit) next[i] = { ...m, y: hit.y + hit.h }
  }
  const queue = [i]
  const pushed = new Set(queue)
  while (queue.length) {
    const q = next[queue.shift()!]
    next.forEach((p, j) => {
      if (pushed.has(j) || !overlap(p, q)) return
      next[j] = { ...p, y: q.y + q.h }
      pushed.add(j)
      queue.push(j)
    })
  }
  return compact(next, i)
}

/** A new panel: in the first gap of ``w`` × ``h`` from the top, else below everything. */
export function add(panels: Panel[], node: Node, w = 8, h = 6): Panel[] {
  const bottom = rows(panels)
  for (let y = 0; y <= bottom; y++) {
    for (let x = 0; x + w <= COLS; x++) {
      const box = { x, y, w, h }
      if (!panels.some((q) => overlap(box, q))) return [...panels, { ...box, node }]
    }
  }
  return [...panels, { x: 0, y: bottom, w, h, node }]
}

export const total = (sections: Section[]) => sections.reduce((n, s) => n + s.panels.length, 0)

/** Where something in a dashboard is: a section, a panel in it, and the path inside its split tree. */
export interface Spot { section: number; panel: number; path: number[] }
export const sameSpot = (a: Spot | null, b: Spot) =>
  !!a && a.section === b.section && a.panel === b.panel && a.path.length === b.path.length && a.path.every((v, i) => v === b.path[i])

/** Mike's example on the grid: the whole hall on the left, a zoomed area top right, the network
 *  bottom right. */
export function starterSections(): Section[] {
  return [{
    panels: [
      { x: 0, y: 0, w: 14, h: 12, node: { pane: planPane() } },
      { x: 14, y: 0, w: 10, h: 6, node: { pane: planPane({ preset: 'ops' }) } },
      { x: 14, y: 6, w: 10, h: 6, node: { pane: planPane({ preset: 'network' }) } },
    ],
  }]
}

export const paneCount = (sections: Section[]) => {
  const count = (n: Node): number => (isPane(n) ? 1 : n.children.reduce((a, c) => a + count(c), 0))
  return sections.reduce((a, s) => a + s.panels.reduce((b, p) => b + count(p.node), 0), 0)
}
