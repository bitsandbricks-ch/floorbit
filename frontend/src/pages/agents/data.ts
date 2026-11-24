import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentGroup, AgentSettingsPage, HostedState } from '@/api/types'
import { useInventoryGroups } from '@/pages/inventory/scope'
import { problems, worst, type Problem, type Tone } from './model'

export type AgentsAnswer = {
  agents: Agent[]; connected: boolean; max: number; server_version?: string; protocol?: number
  groups?: AgentGroup[]; hosted?: HostedState; newest_version?: string | null
}
export type AgentRow = { agent: Agent; problems: Problem[]; tone: Tone }

/** GET /api/agents every 10 s, each agent with what needs a look; the overview and one agent's page share it. */
export function useAgents() {
  const { t, i18n } = useTranslation()
  const query = useQuery({ queryKey: qk.agents, queryFn: () => get<AgentsAnswer>('/api/agents'), refetchInterval: 10_000 })
  const d = query.data
  const rows: AgentRow[] = (d?.agents ?? []).map((a) => {
    const list = problems(a, d?.newest_version, d?.protocol, t, i18n.language)
    return { agent: a, problems: list, tone: worst(list) }
  })
  return { query, data: d, rows }
}

/** The inventory tags an agent can answer for (issue #869: tags took the place of halls). */
export function useAgentTags() {
  const list = useInventoryGroups().data?.tags ?? []
  return {
    names: Object.fromEntries(list.map((x) => [x.id, x.name])) as Record<string, string>,
    options: list.map((x) => ({ value: x.id, label: x.name })),
  }
}

export const agentHref = (id: string) => `/settings/agents/${encodeURIComponent(id)}`

/** One agent's settings page: fields, values with their source, plugin overrides, key and certificate state. */
export function useAgentSettings(agentId: string) {
  return useQuery({ queryKey: [...qk.agents, agentId, 'settings'], queryFn: () => get<AgentSettingsPage>(`/api/agents/${agentId}/settings`) })
}
