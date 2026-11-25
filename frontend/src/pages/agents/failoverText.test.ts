import { describe, expect, it } from 'vitest'
import type { AgentGroup } from '@/api/types'
import { failoverText } from './failoverText'

const t = (k: string, o?: Record<string, unknown>) => `${k}${o ? ` ${JSON.stringify(o)}` : ''}`
type Member = AgentGroup['agents'][number]
const m = (id: string, role: Member['role']): Member => ({ id, name: id.toUpperCase(), connected: role !== 'offline', role, holds: [] })
const group = (primary: string | null, ...agents: Member[]): AgentGroup =>
  ({ id: 'x', tags: ['x'], label: 'Hall', state: 'ok', mode: null, primary, agents, vips: [] })

describe('failoverText', () => {
  it('says who takes over, or that nobody does', () => {
    expect(failoverText('a', group('a', m('a', 'primary')), t)).toBe('agentDetail.failover.alone')
    expect(failoverText('a', group('a', m('a', 'primary'), m('b', 'standby')), t))
      .toBe('agentDetail.failover.takesOver {"names":"B","count":1}')
    expect(failoverText('a', group('a', m('a', 'primary'), m('b', 'offline')), t)).toBe('agentDetail.failover.noStandby')
    expect(failoverText('b', group('a', m('a', 'primary'), m('b', 'standby')), t)).toBe('agentDetail.failover.standsBy {"name":"A"}')
    expect(failoverText('b', group('a', m('a', 'primary'), m('b', 'offline')), t)).toBe('agentDetail.failover.coveredBy {"name":"A"}')
    expect(failoverText('b', group(null, m('a', 'offline'), m('b', 'offline')), t)).toBe('agentDetail.failover.uncovered')
    expect(failoverText('a', group(null, m('a', 'active'), m('b', 'active')), t)).toBe('agentDetail.failover.shares {"names":"B"}')
  })
})
