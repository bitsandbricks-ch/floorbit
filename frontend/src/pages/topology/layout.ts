import type { SwitchLink, TopologyNode, TopologyUplink } from '@/api/types'

export const NODE_W = 120
export const NODE_H = 36
const GAP_X = 18
const GAP_Y = 84
const PER_ROW = 10

export interface Placed { node: TopologyNode; x: number; y: number; level: number }
export interface Layout { placed: Map<string, Placed>; width: number; height: number; loose: TopologyNode[] }

/** Layers from the top of the network down: routers and firewalls first (or the switch with the
 *  most links), then whatever hangs off them, breadth first. A layer wider than PER_ROW wraps, so a
 *  hall of 100 access switches stays readable. Switches without a link are left for a list. */
export function layout(nodes: TopologyNode[], links: SwitchLink[]): Layout {
  const byName = new Map(nodes.map((n) => [n.name.toLowerCase(), n]))
  const near = new Map<string, Set<string>>()
  for (const l of links) {
    const a = l.a.toLowerCase(), b = l.b.toLowerCase()
    if (!byName.has(a) || !byName.has(b)) continue
    if (!near.has(a)) near.set(a, new Set())
    if (!near.has(b)) near.set(b, new Set())
    near.get(a)!.add(b)
    near.get(b)!.add(a)
  }
  const linked = nodes.filter((n) => near.has(n.name.toLowerCase()))
  const loose = nodes.filter((n) => !near.has(n.name.toLowerCase()))
  const level = new Map<string, number>()
  const degree = (n: TopologyNode) => near.get(n.name.toLowerCase())?.size ?? 0
  const byName2 = (x: TopologyNode, y: TopologyNode) => x.name.localeCompare(y.name, undefined, { numeric: true })
  // Each connected part from its own top, so a second hall without a link to the core still shows.
  while (level.size < linked.length) {
    const rest = linked.filter((n) => !level.has(n.name.toLowerCase()))
    const tops = rest.filter((n) => n.role === 'router' || n.role === 'firewall')
    const start = tops.length ? tops : [rest.slice().sort((x, y) => degree(y) - degree(x) || byName2(x, y))[0]]
    let wave = start.map((n) => n.name.toLowerCase())
    wave.forEach((k) => level.set(k, 0))
    for (let depth = 1; wave.length; depth++) {
      const next: string[] = []
      for (const k of wave) for (const m of near.get(k) ?? []) if (!level.has(m)) { level.set(m, depth); next.push(m) }
      wave = next
    }
  }
  const layers: TopologyNode[][] = []
  for (const n of linked) (layers[level.get(n.name.toLowerCase())!] ??= []).push(n)
  const placed = new Map<string, Placed>()
  let y = 0, width = 0
  layers.forEach((layer, depth) => {
    // Under their parents, roughly: sort by where the nodes they hang off sit.
    const pull = (n: TopologyNode) => {
      const xs = [...(near.get(n.name.toLowerCase()) ?? [])].map((k) => placed.get(k)?.x).filter((v): v is number => v != null)
      return xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : 0
    }
    layer.sort((p, q) => pull(p) - pull(q) || byName2(p, q))
    for (let i = 0; i < layer.length; i += PER_ROW) {
      const row = layer.slice(i, i + PER_ROW)
      row.forEach((node, j) => placed.set(node.name.toLowerCase(), { node, x: j * (NODE_W + GAP_X), y, level: depth }))
      width = Math.max(width, row.length * (NODE_W + GAP_X) - GAP_X)
      y += NODE_H + GAP_Y
    }
  })
  // Centre each row under the widest one.
  const rows = new Map<number, Placed[]>()
  for (const p of placed.values()) rows.set(p.y, [...(rows.get(p.y) ?? []), p])
  for (const row of rows.values()) {
    const used = row.length * (NODE_W + GAP_X) - GAP_X
    for (const p of row) p.x += (width - used) / 2
  }
  return { placed, width: Math.max(width, NODE_W), height: Math.max(y - GAP_Y, NODE_H), loose: loose.sort(byName2) }
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
