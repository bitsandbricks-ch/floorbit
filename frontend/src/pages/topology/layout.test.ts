import { describe, expect, it } from 'vitest'
import type { SwitchLink, TopologyNode } from '@/api/types'
import { gbit, layout } from './layout'

const node = (name: string, role = 'switch'): TopologyNode => ({ id: name, name, role, hall: '', unread: false })
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
})
