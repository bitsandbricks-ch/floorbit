import type { AgentGroup } from '@/api/types'
import type { AgentRow } from './data'
import { behind, type Tone } from './model'

// The Local agents list's model (#1463): agents in their groups, what passes the filters.

/** How a group's failover stands, as a colour (floorbit/agent_ha.py STATES). */
export const STATE_COLOR: Record<AgentGroup['state'], string> = {
  ok: 'up', single: 'gray', degraded: 'warn', no_primary: 'down', no_vrrp: 'warn', split: 'down', down: 'down',
}

/** GET /api/agents/load: each agent's last hour of work (telemetry points and syslog lines per minute). */
export interface AgentLoad { hours: number; agents: Record<string, { load: [number, number][]; syslog: number | null }> }

export type Role = 'primary' | 'active' | 'standby' | 'alone' | 'offline'
export interface ListRow extends AgentRow { role: Role; devices: number | null; syslog: number | null; load: number[]; old: boolean }
export interface ListGroup { id: string; label: string; state: AgentGroup['state'] | null; tags: string[]; rows: ListRow[]; tone: Tone }

/** The look of a filter: who is shown. */
export const SHOW = ['all', 'look', 'offline', 'old'] as const
export const FILTERS = { show: 'all', group: 'any' }

export const SEVERITY: Record<Tone, number> = { down: 0, warn: 1, up: 2 }

export const byTone = (a: ListRow, b: ListRow) => SEVERITY[a.tone] - SEVERITY[b.tone] || a.agent.name.localeCompare(b.agent.name)

/** The agents in their groups (the agents with the same tags, floorbit/agent_ha.py), the groups and
 *  the agents in them with what needs a look first. An agent no group names gets one of its own. */
export function groupRows(rows: AgentRow[], groups: AgentGroup[] | undefined, newest: string | null | undefined,
  load: AgentLoad | undefined, unnamed: string): ListGroup[] {
  const placed = new Set<string>()
  const made = (groups ?? []).map((g) => {
    const members = rows.filter((r) => g.agents.some((m) => m.id === r.agent.id))
    members.forEach((r) => placed.add(r.agent.id))
    return { g, members }
  })
  const rest = rows.filter((r) => !placed.has(r.agent.id))
  const all = [
    ...made,
    ...rest.map((r) => ({ g: null as AgentGroup | null, members: [r] })),
  ]
  return all.filter((x) => x.members.length).map(({ g, members }) => {
    const list = members.map((r): ListRow => {
      const a = r.agent
      const said = g?.agents.find((m) => m.id === a.id)?.role
      const role: Role = !a.connected ? 'offline' : members.length === 1 ? 'alone' : said && said !== 'offline' ? said : 'active'
      const heard = a.report?.plugins?.telemetry?.metrics?.devices_heard
      const mine = load?.agents[a.id]
      return {
        ...r, role, devices: typeof heard === 'number' ? heard : null,
        syslog: a.connected && mine?.syslog != null ? mine.syslog / 60 : null,
        load: (mine?.load ?? []).map(([, v]) => v), old: !!a.outdated || behind(a, newest),
      }
    }).sort(byTone)
    const tone = list[0]?.tone ?? 'up'
    return {
      id: g?.id ?? `agent:${members[0].agent.id}`, label: g?.label || (g ? unnamed : members[0].agent.name),
      state: g?.state ?? null, tags: g?.tags ?? [], rows: list, tone,
    }
  }).sort((a, b) => SEVERITY[a.tone] - SEVERITY[b.tone] || worstCount(b) - worstCount(a) || a.label.localeCompare(b.label))
}

// Of two groups equally bad, the one with more agents in that state comes first.
const worstCount = (g: ListGroup) => g.rows.filter((r) => r.tone === g.tone).length

/** Whether a row passes the search and the "show" filter. */
export function matches(r: ListRow, show: string, needle: string, groupLabel = ''): boolean {
  if (show === 'look' && r.tone === 'up') return false
  if (show === 'offline' && r.agent.connected) return false
  if (show === 'old' && !r.old) return false
  if (!needle) return true
  const hay = [r.agent.name, r.agent.address, r.agent.version, groupLabel, ...r.problems.map((p) => p.text)]
  return hay.filter(Boolean).join(' ').toLowerCase().includes(needle)
}

