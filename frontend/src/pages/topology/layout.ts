import type { SwitchLink, TopologyNode } from '@/api/types'

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

/** 1e10 -> "10G", 1e8 -> "100M". */
export function gbit(bps: number | null) {
  if (bps == null) return ''
  return bps >= 1e9 ? `${+(bps / 1e9).toFixed(1)}G` : `${Math.round(bps / 1e6)}M`
}
