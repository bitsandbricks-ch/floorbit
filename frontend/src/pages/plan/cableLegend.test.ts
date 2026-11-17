import { describe, expect, it } from 'vitest'
import type { PlanCable, PlanLink } from '@/api/types'
import { cableSummary, uplinkSummary } from './cableLegend'

const cable = (over: Partial<PlanCable>) => ({ key: Math.random().toString(), kind: 'lan', ref: { cable: 'c' }, ...over }) as PlanCable

describe('the Network layer legend', () => {
  it('lists only the media and speeds on the plan, in a fixed order', () => {
    const s = cableSummary([cable({ media: 'fiber', speed: 10 }), cable({}), cable({ media: 'copper', speed: 1 }), cable({ kind: 'uplink', media: 'dac', speed: 100 })])
    expect(s.media).toEqual(['copper', 'fiber'])
    expect(s.speeds).toEqual([1, 10])
    expect(s.total).toBe(3)
  })
  it('counts cables only read from the ports', () => {
    expect(cableSummary([cable({ ref: {} }), cable({})]).learned).toBe(1)
  })
})

describe('the uplinks in the legend', () => {
  it('counts the links and their trouble', () => {
    const link = (a: string, b: string, issue: '' | 'down' | 'slow' = ''): PlanLink => ({ id: a + b, a, b, type: '', media: '', speed: null, issue })
    expect(uplinkSummary([link('core', 'sw1', 'down'), link('core', 'sw2', 'slow'), link('core', 'sw3')])).toEqual({ total: 3, down: 1, slow: 1 })
  })
})
