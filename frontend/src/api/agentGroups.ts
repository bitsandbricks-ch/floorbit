// One group of local agents (floorbit/blueprints/agent_groups.py): the agents with the same tags,
// which back each other up and split their devices (#1441).
import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { qk } from './keys'
import type { AgentGroup } from './types'

export type AgentGroupMember = AgentGroup['agents'][number] & {
  address: string; version: string; follows_split: boolean; owns: number; pinned: number
}
export type AgentGroupDetail = Omit<AgentGroup, 'agents'> & { agents: AgentGroupMember[]; split: boolean; devices: number }

export const agentGroupUrl = (id: string) => `/api/agents/groups/${encodeURIComponent(id)}`

/** GET /api/agents/groups/<id> every 10 s, as the Local agents list. */
export function useAgentGroup(id: string) {
  return useQuery({ queryKey: [...qk.agents, 'group', id], queryFn: () => get<AgentGroupDetail>(agentGroupUrl(id)), refetchInterval: 10_000 })
}
