// The agents' own updates (floorbit/agent_updates.py, floorbit-agent #98).

/** Where an agent's own update stands, worked out by Floorbit for its page. */
export type SelfUpdateState =
  | 'current' | 'updating' | 'installing' | 'approve' | 'off' | 'image' | 'pull' | 'floorbit'
  | 'refused' | 'rolled_back' | 'none'

export interface SelfUpdateStatus {
  /** The newest agent release this Floorbit has, or null when it couldn't fetch one yet. */
  latest: string | null
  state: SelfUpdateState
  /** The agent's own words when it waits (``refused: ...``). */
  why: string
}

export interface AgentUpdateEvent {
  at: number
  event: 'installed' | 'kept' | 'rolled back' | 'refused' | 'dropped'
  version: string
  detail: string
}

/** What the agent says about its own updates (its report's ``agent_update``). */
export interface AgentSelfUpdateReport {
  policy: 'auto' | 'approve' | 'off'
  running: string
  image: string
  trial: boolean
  rolled_back: string[]
  events: AgentUpdateEvent[]
}
