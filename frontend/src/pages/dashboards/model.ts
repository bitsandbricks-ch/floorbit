import type { PlanDrawing } from '@/api/types'
import type { View } from '../plan/model'
import type { PresetId } from '../plan/layers'
import type { LabelMode } from '../plan/labels'
import type { Section } from './grid'
import type { KindPick, LevelPin } from '@/widgets/level'
import type { LineStyle, Stack, Trend } from '@/widgets/kinds/shape'
import type { Calc } from '@/widgets/kinds/combine'

/** Dashboards (floorbit/dashboards.py): widgets on a grid (grid.ts), each one pane or panes split
 *  side by side or stacked, saved under a name. */

export type Area =
  | { kind: 'hall' }
  | { kind: 'block'; id: string }
  | { kind: 'zone'; id: string }
  | { kind: 'box'; x: number; y: number; w: number; h: number }

export type PlanFilter = 'all' | 'problems' | 'offline' | 'recent' | 'note' | 'checked_in'

/** Plan marks a plan pane draws: all its layers show, only the public ones (Overview, Safety, as on
 *  the attendee pages) for a screen people walk past, or none. */
export type MarksMode = 'all' | 'public' | 'none'
export const MARKS_MODES: MarksMode[] = ['all', 'public', 'none']
export const PUBLIC_MARK_LAYERS = ['overview', 'safety']

export type TextSize = 's' | 'm' | 'l' | 'xl'
export const TEXT_SIZES: TextSize[] = ['s', 'm', 'l', 'xl']
export const TEXT_MAX = 2000

/** ``hide_title`` leaves the pane's head off; the title still names it for screen readers. */
type Head = { title?: string; hide_title?: boolean }

export type Pane = Head & (
  | { kind: 'plan'; hall: string; area: Area; preset: PresetId; show: PlanFilter; labels: LabelMode; marks?: MarksMode }
  /** ``type`` draws the data as another kind (a status as a count), ``level`` pins S, M or L
   *  instead of picking it from the box (issue #924). ``stack``, ``style`` and ``trend`` say how
   *  bars and lines draw. ``also`` adds up to three more tiles to draw with it, ``group_by`` and
   *  ``reduce`` group or calculate before drawing, ``legend`` picks a graph legend's numbers
   *  (issue #959). All are left out when automatic or the default. */
  | { kind: 'tile'; tile: string; type?: KindPick; level?: LevelPin; stack?: Stack; style?: LineStyle; trend?: Trend
      also?: string[]; group_by?: string; reduce?: Calc; legend?: Calc[] }
  /** ``expanded``: the widget at its big size right on the grid (a pane that fills a screen). */
  | { kind: 'view'; view: string; expanded?: boolean }
  | { kind: 'text'; text: string; size: TextSize; align: 'start' | 'center' }
  | { kind: 'empty' }
  /** Only on a public dashboard read signed out: a pane that needs an account (floorbit/dashboards.py). */
  | { kind: 'private' }
)

export type PaneKind = Exclude<Pane['kind'], 'private'>
export const PANE_KINDS: PaneKind[] = ['plan', 'view', 'tile', 'text', 'empty']

export type Split = 'row' | 'column'
export type Node = { pane: Pane } | { split: Split; sizes: number[]; children: Node[] }

export interface Board {
  id: string
  name: string
  sections: Section[]
  /** Rows stretch so the whole dashboard fills the screen (a wall); otherwise the page scrolls. */
  fit: boolean
  /** Seconds per hall on the plan panes that show a whole hall; missing is no rotation. */
  cycle?: number
  updated_at?: number
  by?: string | null
  /** Ready-made (the Kiosk): saving under its id keeps your own version instead. */
  builtin?: boolean
  /** Opens without signing in, showing only what anyone may see. */
  public?: boolean
}

/** A dashboard's name to show: the ready-made ones have theirs in every language. */
export const boardName = (t: (key: string, opts?: Record<string, unknown>) => string, b: Pick<Board, 'id' | 'name' | 'builtin'>) =>
  (b.builtin ? t(`dashboards.builtinName.${b.id}`, { defaultValue: b.name }) : b.name)

/** Panes on a whole dashboard, all panels and their splits together. */
export const MAX_PANES = 40
export const MAX_DEPTH = 4

/** Where a node sits in the tree: the child index at each split on the way down. */
export type Path = number[]

export const planPane = (over: Partial<Extract<Pane, { kind: 'plan' }>> = {}): Pane =>
  ({ kind: 'plan', hall: '', area: { kind: 'hall' }, preset: 'overview', show: 'all', labels: 'auto', marks: 'all', ...over })

/** Mike's example: the whole hall on the left, a zoomed area top right, the network bottom right. */
export function starter(): Node {
  return {
    split: 'row', sizes: [60, 40], children: [
      { pane: planPane() },
      { split: 'column', sizes: [50, 50], children: [{ pane: planPane({ preset: 'ops' }) }, { pane: planPane({ preset: 'network' }) }] },
    ],
  }
}

export const isPane = (n: Node): n is { pane: Pane } => 'pane' in n

export function at(root: Node, path: Path): Node | null {
  let n: Node = root
  for (const i of path) {
    if (isPane(n)) return null
    const next: Node | undefined = n.children[i]
    if (!next) return null
    n = next
  }
  return n
}

/** ``root`` with the node at ``path`` replaced by ``fn(node)`` (null takes it out). */
export function update(root: Node, path: Path, fn: (n: Node) => Node | null): Node | null {
  if (!path.length) return fn(root)
  if (isPane(root)) return root
  const [i, ...rest] = path
  const child = update(root.children[i], rest, fn)
  if (child) {
    const children = root.children.map((c, j) => (j === i ? child : c))
    return { ...root, children }
  }
  // A part taken out: its share goes to the others; a split left with one part becomes that part.
  const children = root.children.filter((_, j) => j !== i)
  const sizes = shares(root.sizes.filter((_, j) => j !== i))
  return children.length === 1 ? children[0] : { ...root, children, sizes }
}

export function panes(root: Node): number {
  return isPane(root) ? 1 : root.children.reduce((n, c) => n + panes(c), 0)
}

export function depth(root: Node): number {
  return isPane(root) ? 0 : 1 + Math.max(...root.children.map(depth))
}

/** The pane at ``path`` split in two: the same split direction adds a part next to it (up to four),
 *  another direction nests a new split. The new part starts empty. */
export function split(root: Node, path: Path, dir: Split): Node {
  if (panes(root) >= MAX_PANES) return root
  const parentPath = path.slice(0, -1)
  const parent = path.length ? at(root, parentPath) : null
  const i = path[path.length - 1]
  if (parent && !isPane(parent) && parent.split === dir && parent.children.length < 4) {
    return update(root, parentPath, (p) => {
      if (isPane(p)) return p
      const children = [...p.children.slice(0, i + 1), { pane: { kind: 'empty' } } as Node, ...p.children.slice(i + 1)]
      const half = p.sizes[i] / 2
      const sizes = [...p.sizes.slice(0, i), half, half, ...p.sizes.slice(i + 1)]
      return { ...p, children, sizes }
    }) ?? root
  }
  if (path.length >= MAX_DEPTH) return root
  return update(root, path, (n) => ({ split: dir, sizes: [50, 50], children: [n, { pane: { kind: 'empty' } }] })) ?? root
}

export function remove(root: Node, path: Path): Node {
  if (!path.length) return { pane: { kind: 'empty' } }
  return update(root, path, () => null) ?? { pane: { kind: 'empty' } }
}

export function setPane(root: Node, path: Path, pane: Pane): Node {
  return update(root, path, () => ({ pane })) ?? root
}

/** The split at ``path`` with the border after part ``i`` moved to ``pct`` percent of the split. */
export function resize(root: Node, path: Path, i: number, pct: number): Node {
  return update(root, path, (n) => {
    if (isPane(n)) return n
    const before = n.sizes.slice(0, i).reduce((a, b) => a + b, 0)
    const pair = n.sizes[i] + n.sizes[i + 1]
    const left = Math.min(pair - 5, Math.max(5, pct - before))
    const sizes = n.sizes.map((s, j) => (j === i ? left : j === i + 1 ? pair - left : s))
    return { ...n, sizes: sizes.map((s) => Math.round(s * 100) / 100) }
  }) ?? root
}

function shares(sizes: number[]): number[] {
  const total = sizes.reduce((a, b) => a + b, 0) || 1
  return sizes.map((s) => Math.round((s * 10000) / total) / 100)
}

/** A layout id from its name, as the server takes it. */
export const slug = (name: string) =>
  name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32) || 'screen'

/** Everything drawn on a hall (seat blocks, zones, walls, labels), in drawing units, for "the whole
 *  hall" on a big screen: the drawing's own box leaves room for editing that a screen doesn't need. */
export function contentBox(drawing: PlanDrawing, margin = 40): View | null {
  const xs: number[] = [], ys: number[] = []
  for (const b of drawing.shapes) {
    const r = ((b.rotation % 180) + 180) % 180
    const rad = (r * Math.PI) / 180
    const hw = (Math.abs(Math.cos(rad)) * b.w + Math.abs(Math.sin(rad)) * b.h) / 2 + 6
    const hh = (Math.abs(Math.sin(rad)) * b.w + Math.abs(Math.cos(rad)) * b.h) / 2 + 6
    xs.push(b.cx - hw, b.cx + hw)
    ys.push(b.cy - hh - 40, b.cy + hh)   // room for the block's name above it
  }
  for (const m of drawing.marks ?? []) {
    xs.push(m.x)
    ys.push(m.y)
    if (m.kind === 'zone') { xs.push(m.x + (m.w ?? 0)); ys.push(m.y + (m.h ?? 0)) }
    if (m.kind === 'wall') { xs.push(m.x2 ?? m.x); ys.push(m.y2 ?? m.y) }
  }
  if (!xs.length) return null
  const x0 = Math.min(...xs) - margin, y0 = Math.min(...ys) - margin
  return { x: x0, y: y0, w: Math.max(...xs) + margin - x0, h: Math.max(...ys) + margin - y0 }
}

/** The part of the hall a plan pane shows, or null when it names something no longer there. */
export function areaView(area: Area, drawing: PlanDrawing): View | null {
  if (area.kind === 'box') return { x: area.x, y: area.y, w: area.w, h: area.h }
  if (area.kind === 'zone') {
    const z = drawing.marks?.find((m) => m.kind === 'zone' && m.id === area.id)
    return z ? pad({ x: z.x, y: z.y, w: z.w ?? 0, h: z.h ?? 0 }, 24) : null
  }
  if (area.kind === 'block') {
    const b = drawing.shapes.find((s) => s.name === area.id)
    if (!b) return null
    return contentBox({ ...drawing, shapes: [b], marks: [] }, 24)
  }
  return contentBox(drawing)
}

const pad = (v: View, m: number): View => ({ x: v.x - m, y: v.y - m, w: v.w + 2 * m, h: v.h + 2 * m })

/** The seats whose middle lies inside ``view``: the seats a pane is about. */
export function seatsIn(drawing: PlanDrawing, view: View): string[] {
  const out: string[] = []
  for (const b of drawing.shapes) {
    const rad = (b.rotation * Math.PI) / 180, cos = Math.cos(rad), sin = Math.sin(rad)
    for (const c of b.cells) {
      // Like plan/model.ts seatCenter, for every seat at once.
      const lx = c.x + drawing.cell / 2, ly = c.y + drawing.cell / 2
      const x = b.cx + lx * cos - ly * sin, y = b.cy + lx * sin + ly * cos
      if (x >= view.x && x <= view.x + view.w && y >= view.y && y <= view.y + view.h) out.push(c.seat)
    }
  }
  return out
}
