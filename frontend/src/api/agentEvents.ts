// One agent's recent events (floorbit/blueprints/agent_events.py, issue #905).
import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { qk } from './keys'

export interface AgentEvent {
  /** Seconds since the epoch. */
  at: number | null
  /** Who did it: an admin's name, or "agent" for what the agent reported itself. */
  user: string | null
  area: string
  /** In the page's language. */
  action: string
  ok: boolean
}

/** What the audit log holds about this agent, newest first; refreshed with the agents list. */
export function useAgentEvents(agentId: string, limit = 50) {
  return useQuery({
    queryKey: [...qk.agents, agentId, 'events', limit],
    queryFn: () => get<{ events: AgentEvent[] }>(`/api/agents/${encodeURIComponent(agentId)}/events?limit=${limit}`),
    refetchInterval: 30_000,
  })
}
