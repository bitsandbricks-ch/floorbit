import { describe, expect, it } from 'vitest'
import type { SwitchLink, TopologyNode, TopologyUplink } from '@/api/types'
import { NODE_W, gbit, layout, placeUplinks } from './layout'

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

  it('wraps a wide layer into rows', () => {
    const access = Array.from({ length: 25 }, (_, i) => node(`sw-${i}`))
    const { placed } = layout([node('dist-01'), ...access], access.map((n) => link('dist-01', n.name)))
    expect(new Set(access.map((n) => placed.get(n.name)!.y)).size).toBe(3)
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
})
