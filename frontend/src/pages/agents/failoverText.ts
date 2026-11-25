import type { AgentGroup } from '@/api/types'

/** Who takes over when this agent stops, or whose work it does (issue #905): its group in one line. */
export function failoverText(agentId: string, g: AgentGroup, t: (k: string, o?: Record<string, unknown>) => string): string {
  const me = g.agents.find((a) => a.id === agentId)
  const others = g.agents.filter((a) => a.id !== agentId)
  const live = others.filter((a) => a.connected).map((a) => a.name)
  const primary = g.agents.find((a) => a.id === g.primary)
  if (!others.length) return t('agentDetail.failover.alone')
  if (!me || me.role === 'offline') {
    return primary ? t('agentDetail.failover.coveredBy', { name: primary.name }) : t('agentDetail.failover.uncovered')
  }
  if (me.role === 'primary') {
    return live.length ? t('agentDetail.failover.takesOver', { names: live.join(', '), count: live.length }) : t('agentDetail.failover.noStandby')
  }
  if (me.role === 'standby') {
    return primary ? t('agentDetail.failover.standsBy', { name: primary.name }) : t('agentDetail.failover.noPrimary')
  }
  return t('agentDetail.failover.shares', { names: live.join(', ') || '–' })
}
