import type { SwitchLink, TopologyNode, TopologyUplink } from '@/api/types'

/** One device's slot: the floor plan's 24x16 glyph on top, its 11px name under it (#1331). */
export const NODE_W = 64
export const NODE_H = 34
/** Where the glyph sits in its slot: centred, its middle this far down. */
export const GLYPH_Y = 9
const GLYPH_HALF = 8
const GAP_X = 8
const GAP_Y = 40
const GAP_LEAF = 26 // between rows of end boxes under one parent: room for their own bus
const GAP_TREE = 24 // between the blocks of two parents side by side
const LEAF_COLS = 5

export interface Placed { node: TopologyNode; x: number; y: number; level: number }
export interface Layout {
  placed: Map<string, Placed>; width: number; height: number; loose: TopologyNode[]
  /** Each box's parent in the tree, by lower-case name: the links the routing draws as a bus. */
  parent: Map<string, string>
}

/** A tree from the top of the network down (#1050): routers first (firewalls when there is no
 *  router, else the switch with the most links), then whatever hangs off them, breadth first. Each
 *  box sits over its own branch, so a distribution switch has its access switches under it, and the
 *  boxes with nothing below them (access switches, firewalls) wrap into a small grid under their
 *  parent instead of one long row. Switches without a link are left for a list. */
export function layout(nodes: TopologyNode[], links: SwitchLink[]): Layout {
  const byName = new Map(nodes.map((n) => [n.name.toLowerCase(), n]))
  const near = new Map<string, Set<string>>()
  for (const l of links) {
    const a = l.a.toLowerCase(), b = l.b.toLowerCase()
    if (!byName.has(a) || !byName.has(b) || a === b) continue
    if (!near.has(a)) near.set(a, new Set())
    if (!near.has(b)) near.set(b, new Set())
    near.get(a)!.add(b)
    near.get(b)!.add(a)
  }
  const linked = nodes.filter((n) => near.has(n.name.toLowerCase()))
  const loose = nodes.filter((n) => !near.has(n.name.toLowerCase()))
  const level = new Map<string, number>()
  const parent = new Map<string, string>()
  const roots: string[] = []
  const degree = (n: TopologyNode) => near.get(n.name.toLowerCase())?.size ?? 0
  const byName2 = (x: TopologyNode, y: TopologyNode) => x.name.localeCompare(y.name, undefined, { numeric: true })
  const keyOrder = (x: string, y: string) => byName2(byName.get(x)!, byName.get(y)!)
  // Each connected part from its own top, so a second hall without a link to the core still shows.
  while (level.size < linked.length) {
    const rest = linked.filter((n) => !level.has(n.name.toLowerCase()))
    const routers = rest.filter((n) => n.role === 'router')
    const tops = routers.length ? routers : rest.filter((n) => n.role === 'firewall')
    const start = tops.length ? tops.slice().sort(byName2) : [rest.slice().sort((x, y) => degree(y) - degree(x) || byName2(x, y))[0]]
    let wave = start.map((n) => n.name.toLowerCase())
    wave.forEach((k) => { level.set(k, 0); roots.push(k) })
    for (let depth = 1; wave.length; depth++) {
      const next: string[] = []
      for (const k of wave) {
        for (const m of [...(near.get(k) ?? [])].sort(keyOrder)) {
          if (!level.has(m)) { level.set(m, depth); parent.set(m, k); next.push(m) }
        }
      }
      wave = next
    }
  }
  const kids = new Map<string, string[]>()
  for (const [k, p] of parent) kids.set(p, [...(kids.get(p) ?? []), k])
  for (const list of kids.values()) list.sort(keyOrder)

  // Measure each branch bottom-up, then place it top-down at its left edge.
  const size = new Map<string, { w: number; h: number }>()
  const leafGrid = (n: number) => {
    const cols = Math.min(n, LEAF_COLS), rows = Math.ceil(n / LEAF_COLS)
    return { w: cols * (NODE_W + GAP_X) - GAP_X, h: rows * (NODE_H + GAP_LEAF) - GAP_LEAF }
  }
  const split = (k: string) => {
    const all = kids.get(k) ?? []
    return { branches: all.filter((c) => kids.has(c)), leaves: all.filter((c) => !kids.has(c)) }
  }
  const measure = (k: string): { w: number; h: number } => {
    const { branches, leaves } = split(k)
    const parts = [...branches.map(measure), ...(leaves.length ? [leafGrid(leaves.length)] : [])]
    const below = parts.length ? parts.reduce((s, p) => s + p.w, 0) + GAP_TREE * (parts.length - 1) : 0
    const got = { w: Math.max(NODE_W, below), h: NODE_H + (parts.length ? GAP_Y + Math.max(...parts.map((p) => p.h)) : 0) }
    size.set(k, got)
    return got
  }
  const placed = new Map<string, Placed>()
  const put = (k: string, x: number, y: number) => {
    const me = size.get(k)!
    placed.set(k, { node: byName.get(k)!, x: x + (me.w - NODE_W) / 2, y, level: level.get(k)! })
    const { branches, leaves } = split(k)
    const parts = [...branches.map((c) => ({ c, ...size.get(c)! })), ...(leaves.length ? [{ c: '', ...leafGrid(leaves.length) }] : [])]
    const used = parts.reduce((s, p) => s + p.w, 0) + GAP_TREE * Math.max(0, parts.length - 1)
    let cx = x + (me.w - used) / 2
    const cy = y + NODE_H + GAP_Y
    for (const part of parts) {
      if (part.c) put(part.c, cx, cy)
      else {
        leaves.forEach((c, i) => placed.set(c, {
          node: byName.get(c)!, level: level.get(c)!,
          x: cx + (i % LEAF_COLS) * (NODE_W + GAP_X), y: cy + Math.floor(i / LEAF_COLS) * (NODE_H + GAP_LEAF),
        }))
      }
      cx += part.w + GAP_TREE
    }
  }
  let x = 0, height = 0
  for (const r of roots) {
    const { w, h } = measure(r)
    put(r, x, 0)
    x += w + GAP_TREE
    height = Math.max(height, h)
  }
  return { placed, width: Math.max(x - GAP_TREE, NODE_W), height: Math.max(height, NODE_H), loose: loose.sort(byName2), parent }
}

export interface UplinkBox { uplink: TopologyUplink; x: number; y: number; to: Placed }
export interface WithUplinks { boxes: UplinkBox[]; dx: number; dy: number; width: number; height: number }

/** The internet lines in a row above the diagram, each over the box it comes in at; the diagram
 *  moves down (and right, when a line would stick out on the left) to make room. */
export function placeUplinks(laid: Layout, uplinks: TopologyUplink[]): WithUplinks {
  const shown = uplinks.filter((u) => laid.placed.has(u.device.toLowerCase()))
  if (!shown.length) return { boxes: [], dx: 0, dy: 0, width: laid.width, height: laid.height }
  const byDevice = new Map<string, TopologyUplink[]>()
  for (const u of shown) byDevice.set(u.device.toLowerCase(), [...(byDevice.get(u.device.toLowerCase()) ?? []), u])
  const raw: { uplink: TopologyUplink; x: number; to: Placed }[] = []
  for (const [key, lines] of byDevice) {
    const to = laid.placed.get(key)!
    lines.forEach((uplink, i) => raw.push({ uplink, to, x: to.x + (i - (lines.length - 1) / 2) * (NODE_W + GAP_X) }))
  }
  // Two routers side by side with two lines each would overlap: push each box right of the last.
  raw.sort((a, b) => a.x - b.x)
  for (let i = 1; i < raw.length; i++) raw[i].x = Math.max(raw[i].x, raw[i - 1].x + NODE_W + GAP_X)
  const dx = Math.max(0, -raw[0].x)
  const dy = NODE_H + GAP_Y
  const right = Math.max(laid.width + dx, raw[raw.length - 1].x + dx + NODE_W)
  return { boxes: raw.map((r) => ({ uplink: r.uplink, to: r.to, x: r.x + dx, y: 0 })), dx, dy, width: right, height: laid.height + dy }
}

/** 1e10 -> "10G", 1e8 -> "100M". */
export function gbit(bps: number | null) {
  if (bps == null) return ''
  return bps >= 1e9 ? `${+(bps / 1e9).toFixed(1)}G` : `${Math.round(bps / 1e6)}M`
}

export interface Spot { x: number; y: number }

/** The crew's arrangement over the automatic one (issue: drag and keep it). Boxes without a saved
 *  place keep theirs; the whole picture is moved back to start at 0,0 so the internet row still fits on top. */
export function arranged(laid: Layout, saved: Record<string, Spot> | undefined): Layout {
  if (!saved || !Object.keys(saved).length) return laid
  const placed = new Map<string, Placed>()
  for (const [key, p] of laid.placed) {
    const s = saved[key]
    placed.set(key, s ? { ...p, x: s.x, y: s.y } : { ...p })
  }
  const all = [...placed.values()]
  if (!all.length) return laid
  const minX = Math.min(...all.map((p) => p.x)), minY = Math.min(...all.map((p) => p.y))
  for (const p of all) { p.x -= minX; p.y -= minY }
  const width = Math.max(...all.map((p) => p.x)) + NODE_W, height = Math.max(...all.map((p) => p.y)) + NODE_H
  return { placed, width, height, loose: laid.loose, parent: laid.parent }
}

export interface Spot2 { x: number; y: number }
export interface Route { id: string; d: string }
export interface RunCount { x: number; y: number; count: number }

/** Lines as the floor plan draws cable runs (#1335): out of the bottom of the upper glyph, along a
 *  bus just above the row it goes to, and a short drop into the lower glyph. Children of one parent
 *  share the trunk and the bus, so ten firewalls read as one run with ten drops, not ten crossing
 *  diagonals; a second row under the same parent is reached down a spine left of the rows. Links
 *  outside the tree take the same elbow halfway between the two. Where three or more links share a
 *  trunk it gets a count, like the plan's cable bundles. ``at`` is where each box is drawn now. */
export function routes(links: SwitchLink[], parent: Map<string, string>, at: (key: string) => Spot2 | undefined): { lines: Route[]; counts: RunCount[] } {
  const top = (p: Spot2) => ({ x: p.x + NODE_W / 2, y: p.y + GLYPH_Y - GLYPH_HALF })
  const bottom = (p: Spot2) => ({ x: p.x + NODE_W / 2, y: p.y + GLYPH_Y + GLYPH_HALF })
  const kids = new Map<string, string[]>()
  for (const [k, p] of parent) kids.set(p, [...(kids.get(p) ?? []), k])
  const lines: Route[] = []
  const trunks = new Map<string, { x: number; y1: number; y2: number; count: number }>()
  for (const l of links) {
    const a = l.a.toLowerCase(), b = l.b.toLowerCase()
    const pa = at(a), pb = at(b)
    if (!pa || !pb || a === b) continue
    const tree = parent.get(b) === a ? [a, b] : parent.get(a) === b ? [b, a] : null
    const [up, down] = pa.y <= pb.y ? [pa, pb] : [pb, pa]
    const upKey = pa.y <= pb.y ? a : b
    if (Math.abs(pa.y - pb.y) < NODE_H) {
      // Side by side: over the top of both, clear of their names.
      const s = top(pa), e = top(pb), y = Math.min(s.y, e.y) - GAP_Y / 3
      lines.push({ id: l.id, d: `M${s.x} ${s.y}V${y}H${e.x}V${e.y}` })
      continue
    }
    const s = bottom(up), e = top(down)
    if (tree && tree[0] === upKey) {
      const siblings = (kids.get(tree[0]) ?? []).map(at).filter((p): p is Spot2 => !!p && p.y > up.y)
      const firstRow = Math.min(...siblings.map((p) => p.y))
      const bus1 = top({ x: 0, y: firstRow }).y - GAP_LEAF / 3
      const busHere = e.y - GAP_LEAF / 3
      if (down.y - firstRow < NODE_H / 2) {
        lines.push({ id: l.id, d: `M${s.x} ${s.y}V${bus1}H${e.x}V${e.y}` })
      } else {
        // Left of the lower rows only: further left would run down through a sibling branch.
        const spine = Math.min(...siblings.filter((p) => p.y - firstRow >= NODE_H / 2).map((p) => p.x)) - GAP_X / 2
        lines.push({ id: l.id, d: `M${s.x} ${s.y}V${bus1}H${spine}V${busHere}H${e.x}V${e.y}` })
      }
      const t = trunks.get(tree[0]) ?? { x: s.x, y1: s.y, y2: bus1, count: 0 }
      t.count++
      trunks.set(tree[0], t)
    } else {
      const mid = (s.y + e.y) / 2
      lines.push({ id: l.id, d: `M${s.x} ${s.y}V${mid}H${e.x}V${e.y}` })
    }
  }
  const counts = [...trunks.values()].filter((t) => t.count >= 3).map((t) => ({ x: t.x, y: (t.y1 + t.y2) / 2, count: t.count }))
  return { lines, counts }
}
