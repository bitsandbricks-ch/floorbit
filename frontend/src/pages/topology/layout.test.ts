import { describe, expect, it } from 'vitest'
import type { SwitchLink, TopologyNode, TopologyUplink } from '@/api/types'
import { NODE_H, NODE_W, arranged, gbit, layout, placeUplinks, routes } from './layout'

const node = (name: string, role = 'switch'): TopologyNode => ({ id: name, name, role, hall: '', unread: false, status: 'online' })
const link = (a: string, b: string): SwitchLink => ({
  id: `${a}-${b}`, a, a_port: 'x1', b, b_port: 'x2', type: '', speed: null, note: '', media: '', state: 'up', speed_bps: null, issue: '',
})

describe('topology layout', () => {
  it('puts the router on top, then what hangs off it, and lists switches without links apart', () => {
    const nodes = [node('sw-a-01'), node('core-01', 'router'), node('dist-01'), node('sw-z-99')]
    const { placed, loose } = layout(nodes, [link('sw-a-01', 'dist-01'), link('dist-01', 'core-01')])
    expect([...placed.values()].map((p) => [p.node.name, p.level])).toEqual(
      expect.arrayContaining([['core-01', 0], ['dist-01', 1], ['sw-a-01', 2]]))
    expect(placed.get('core-01')!.y).toBeLessThan(placed.get('dist-01')!.y)
    expect(loose.map((n) => n.name)).toEqual(['sw-z-99'])
  })

  it('hangs firewalls under the router, and puts switches with more below them in the first row', () => {
    // Issue #1050: ten firewalls beside the core read as a chain.
    const fws = Array.from({ length: 12 }, (_, i) => node(`fw-${String(i + 1).padStart(2, '0')}`, 'firewall'))
    const nodes = [node('core-01', 'router'), node('dist-01'), node('sw-a-01'), ...fws]
    const { placed } = layout(nodes, [link('core-01', 'dist-01'), link('dist-01', 'sw-a-01'), ...fws.map((f) => link('core-01', f.name))])
    expect(placed.get('fw-01')!.level).toBe(1)
    expect(placed.get('core-01')!.y).toBeLessThan(placed.get('fw-01')!.y)
    const firstRow = placed.get('dist-01')!.y
    expect(Math.max(...fws.map((f) => placed.get(f.name)!.y))).toBeGreaterThan(firstRow)  // 13 in the layer: it wraps
    expect(fws.every((f) => placed.get(f.name)!.y >= firstRow)).toBe(true)
  })

  it('starts from the firewalls when there is no router', () => {
    const { placed } = layout([node('fw-1', 'firewall'), node('sw-1')], [link('fw-1', 'sw-1')])
    expect(placed.get('fw-1')!.level).toBe(0)
  })

  it('wraps the end boxes under one parent into a small grid', () => {
    const access = Array.from({ length: 25 }, (_, i) => node(`sw-${i}`))
    const { placed } = layout([node('dist-01'), ...access], access.map((n) => link('dist-01', n.name)))
    expect(new Set(access.map((n) => placed.get(n.name)!.y)).size).toBe(5)
    expect(new Set(access.map((n) => placed.get(n.name)!.x)).size).toBe(5)
  })

  it('puts each access switch under its own distribution switch', () => {
    const nodes = [node('core-01', 'router'), node('dist-01'), node('dist-02'), node('sw-a'), node('sw-b')]
    const { placed } = layout(nodes, [link('core-01', 'dist-01'), link('core-01', 'dist-02'), link('dist-01', 'sw-a'), link('dist-02', 'sw-b')])
    const x = (n: string) => placed.get(n)!.x
    expect(x('dist-01')).toBe(x('sw-a'))
    expect(x('dist-02')).toBe(x('sw-b'))
    expect(x('core-01')).toBe((x('dist-01') + x('dist-02')) / 2)
  })

  it('says speeds short', () => {
    expect([gbit(1e10), gbit(1e9), gbit(1e8), gbit(null)]).toEqual(['10G', '1G', '100M', ''])
  })

  it('puts the internet lines in a row above their routers, never overlapping, and moves the diagram down', () => {
    const laid = layout([node('core-01', 'router'), node('core-02', 'router'), node('sw-1')], [link('core-01', 'sw-1'), link('core-02', 'sw-1')])
    const up = (id: string, device: string): TopologyUplink => ({ id, name: id, device, port: 'x', capacity_mbps: 1000, status: 'up', utilization: null })
    const got = placeUplinks(laid, [up('a', 'core-01'), up('b', 'core-01'), up('c', 'core-02'), up('d', 'gone')])
    expect(got.boxes.map((b) => b.uplink.id)).toEqual(['a', 'b', 'c'])
    const xs = got.boxes.map((b) => b.x)
    for (let i = 1; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual(NODE_W)
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(0)
    expect(got.dy).toBeGreaterThan(0)
    expect(got.height).toBe(laid.height + got.dy)
    expect(placeUplinks(laid, [])).toEqual({ boxes: [], dx: 0, dy: 0, width: laid.width, height: laid.height })
  })

  it('puts the boxes where the crew dragged them and starts the picture at 0,0', () => {
    const laid = layout([node('core-01', 'router'), node('sw-1'), node('sw-2')], [link('core-01', 'sw-1'), link('core-01', 'sw-2')])
    expect(arranged(laid, {})).toBe(laid)
    const got = arranged(laid, { 'sw-1': { x: -200, y: 500 }, nope: { x: 1, y: 1 } })
    const sw1 = got.placed.get('sw-1')!, core = got.placed.get('core-01')!
    expect(sw1.x).toBe(0)                                                    // moved right by 200 with everything else
    expect(core.x).toBe(laid.placed.get('core-01')!.x + 200)
    expect(core.y).toBe(0)
    expect(got.height).toBe(500 + NODE_H)
    expect(laid.placed.get('sw-1')!.x).not.toBe(-200)                        // the automatic layout is left as it was
  })

  describe('routes', () => {
    const fws = Array.from({ length: 10 }, (_, i) => node(`fw-${String(i + 1).padStart(2, '0')}`, 'firewall'))
    const nodes = [node('core-01', 'router'), ...fws]
    const links = fws.map((f) => link('core-01', f.name))
    const laid = layout(nodes, links)
    const at = (k: string) => laid.placed.get(k)
    const { lines, counts } = routes(links, laid.parent, at)
    const segments = (d: string) => [...d.matchAll(/([MVH])(-?[\d.]+)(?: (-?[\d.]+))?/g)]

    it('runs every link at right angles', () => {
      expect(lines).toHaveLength(10)
      for (const r of lines) expect(segments(r.d).slice(1).every((m) => m[1] === 'V' || m[1] === 'H')).toBe(true)
    })

    it('shares one trunk and one bus between the children of a box, and counts it', () => {
      const firstTwo = lines.slice(0, 2).map((r) => r.d.split('H')[0])
      expect(firstTwo[0]).toBe(firstTwo[1])                                  // same way down to the bus
      expect(counts).toEqual([expect.objectContaining({ count: 10 })])
    })

    it('reaches a second row down a spine left of the rows, never through the first row', () => {
      const many = Array.from({ length: 12 }, (_, i) => node(`sw-${i}`))
      const ls = many.map((n) => link('dist', n.name))
      const l2 = layout([node('dist'), ...many], ls)
      const got = routes(ls, l2.parent, (k) => l2.placed.get(k))
      const row1 = Math.min(...many.map((n) => l2.placed.get(n.name)!.y))
      const left = Math.min(...many.map((n) => l2.placed.get(n.name)!.x))
      const second = got.lines.find((r) => r.id === 'dist-sw-11')!
      const spine = segments(second.d).find((m) => m[1] === 'H' && Number(m[2]) < left)
      expect(spine).toBeDefined()
      expect(l2.placed.get('sw-11')!.y).toBeGreaterThan(row1)
    })

    it('leaves out links to boxes not drawn and gives a count only from three links up', () => {
      const two = routes([link('core-01', 'fw-01'), link('core-01', 'fw-02'), link('core-01', 'gone')], laid.parent, at)
      expect(two.lines).toHaveLength(2)
      expect(two.counts).toEqual([])
    })
  })
})
