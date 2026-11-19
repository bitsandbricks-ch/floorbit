import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentGroup, Hall, HostedState } from '@/api/types'
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

export function useHalls() {
  const halls = useQuery({ queryKey: qk.halls, queryFn: () => get<{ halls: Hall[] }>('/api/halls') })
  const list = halls.data?.halls ?? []
  return {
    names: Object.fromEntries(list.map((h) => [h.id, h.name])) as Record<string, string>,
    options: list.map((h) => ({ value: h.id, label: h.name })),
  }
}

export const agentHref = (id: string) => `/settings/agents/${encodeURIComponent(id)}`
