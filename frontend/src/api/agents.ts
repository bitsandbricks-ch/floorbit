import type { AgentSelfUpdateReport, SelfUpdateStatus } from './agentUpdates'

/** GET /api/agents (issue #2): the local agents enrolled for a hosted Floorbit. */
export interface Agent {
  id: string; name: string; created_at: number; created_by: string | null
  last_seen: number | null; version: string | null; address: string | null; connected: boolean
  /** The last hour of answers, kept in memory on the server (missing right after enrolling). */
  stats?: AgentStats
  /** The agent protocol it spoke last (1 or 2; null before its first request). */
  protocol?: number | null
  /** Speaks an older agent protocol than this Floorbit: time to pull the new image. */
  outdated?: boolean
  /** Inventory tag ids it answers for (devices with one, directly or by group); empty: every device. */
  tags?: string[]
  /** What it sent in the last ten minutes besides answers: syslog lines kept, flow summaries. */
  relays?: { syslog?: { at: number; count: number }; flows?: { at: number; count: number } }
  /** The agent's own numbers, sent every half minute (null: none lately, or an older agent). */
  report?: AgentReport | null
  /** Plugins that are on here but this agent leaves off (another agent runs them). */
  plugins_off?: string[]
  /** What it can do (floorbit/agent_ha.py CAPABILITIES); Floorbit falls back for the rest. */
  capabilities?: string[]
  /** How it reaches this Floorbit right now: protocol 2's WebSocket link or the HTTPS long poll
   *  (null: not connected, or connected to another instance). */
  transport?: 'websocket' | 'poll' | null
  /** When its key was made, and until when the key before still works (after "New key"). */
  renewed_at?: number
  old_works_until?: number | null
  /** One of the demo's made-up agents (floorbit/agent_demo.py): connected, but takes no calls. */
  demo?: boolean
  /** Where its own update stands (floorbit/agent_updates.py). */
  self_update?: SelfUpdateStatus
}

/** An agent's plugin updates (docs/agent-plugins.md, "Updates"). */
export interface AgentUpdates {
  policy: 'auto' | 'approve' | 'off'
  image: string
  /** Whether the agent's image pins a signing key at all. */
  signed: boolean
  plugins: Record<string, {
    version: string; source: 'image' | 'bundle'; probation: boolean; rolled_back: string[]
    pending: { version: string; why: string } | null
  }>
  events: { at: number; plugin: string; event: 'installed' | 'kept' | 'rolled back' | 'refused' | 'waiting' | 'dropped'; version: string; detail: string }[]
}

/** Agents that serve the same tags, and how their failover stands (floorbit/agent_ha.py). */
export interface AgentGroup {
  id: string
  tags: string[]
  label: string
  state: 'down' | 'split' | 'no_vrrp' | 'no_primary' | 'degraded' | 'single' | 'ok'
  mode: 'active-active' | 'active-passive' | null
  primary: string | null
  agents: { id: string; name: string; connected: boolean; role: 'primary' | 'standby' | 'active' | 'offline'; holds: string[] }[]
  vips: string[]
}

/** This Floorbit's own availability (floorbit/cluster.py). */
export interface HostedState {
  mode: 'single' | 'redis'
  pods: { pod: string; at: number; leader: boolean; me: boolean }[]
  database: { kind: string; ok: boolean; since?: number | null }
  redis: { ok: boolean }
}

export interface AgentReport {
  at: number
  up_seconds?: number
  reconnects?: number
  link_drops?: number
  calls_busy?: number
  answers_failed?: number
  syslog_received?: number
  syslog_sent?: number
  syslog_dropped?: number
  syslog_backlog?: number
  flows_packets?: number
  /** Captive portal answers: the note shown, or not (checked in). */
  captive_shown?: number
  captive_done?: number
  /** Agent plugins (docs/agent-plugins.md): how each one that should run is doing. */
  plugins?: Record<string, AgentPluginHealth>
  updates?: AgentUpdates
  /** Its own updates (floorbit-agent's self_update.py). */
  agent_update?: AgentSelfUpdateReport
  /** With VRRP: whether it is its hall's primary, and the addresses it holds. */
  vrrp?: { primary: boolean; holds: string[] }
  /** Where each of its settings came from (floorbit/agent_settings.py ``clean_report``). */
  settings?: AgentSettingsReport
}

export type SettingSource = 'env' | 'floorbit' | 'default'

/** What the agent says about its settings: their source and value (never a secret's), which wait
 *  for its next start, where its key and certificate came from. */
export interface AgentSettingsReport {
  values: Record<string, { source: SettingSource; value?: string; set?: boolean }>
  pending?: string[]
  key?: 'stored' | 'env' | 'file'
  cert?: { not_after: number; names: string[]; source: SettingSource; floorbit_ca: boolean; public?: boolean }
}

/** One of an agent's own settings (agent_settings.FIELDS). */
export interface AgentSettingField {
  key: string; env: string | null
  type: 'url' | 'listen' | 'secret' | 'int' | 'names' | 'cidrs' | 'ips' | 'iface' | 'choice'
  default: string | number | string[]; restart: boolean; min?: number; max?: number; options?: string[]
}

/** A plugin setting an agent may set for itself (Settings > Plugins has the default). */
export interface AgentPluginField {
  key: string; label: string; type: string; help?: string | null; placeholder?: string | null
  min?: number | null; max?: number | null; options?: { value: string; label: string }[] | null
  default: unknown
}

/** GET /api/agents/<id>/settings. */
export interface AgentSettingsPage {
  fields: AgentSettingField[]
  /** What Floorbit sets; a secret is ``true`` (set) and never sent back. */
  values: Record<string, string | number | string[] | true>
  local_only: string[]
  plugins: { id: string; name: string; fields: AgentPluginField[]; values: Record<string, unknown> }[]
  roll_asked: number | null
  renewed_at: number | null
  cert: { issued_at: number; not_after: number; names: string[] } | null
  cert_asked: number | null
  /** The agent's own key, pinned by Floorbit; it signs every request (floorbit/agent_identity.py). */
  identity?: { fingerprint: string; not_after: number; pinned_at: number; issued_at: number } | null
  /** The tenant's Let's Encrypt certificate, when the platform has a domain for the agents. */
  public_cert?: {
    name: string; not_after: number | null; issued_at: number | null; error: string | null; failed_at: number | null
    /** Why the name doesn't reach Floorbit yet (public DNS, port 80); nothing is ordered until it does. */
    waiting?: string | null; checked_at?: number | null
  } | null
  /** When this agent last took that certificate's key. */
  public_cert_at?: number | null
}

export interface AgentPluginHealth {
  status: 'ok' | 'warning' | 'error' | 'off'
  message: string
  /** A code the page turns into a translated sentence with a link (agents.hint.*), when known. */
  hint?: string
  running: boolean
  metrics: Record<string, number>
  errors: { at: number | null; error: string }[]
  /** Logins the plugin stopped trying until a tech clears them (docs/agent-plugins.md). */
  auth_blocked?: { device: string; credential: string; rev: string | null; since: number | null; message: string }[]
}

export interface AgentStats {
  calls: number; failed: number; median_ms: number | null
  last_error: { at: number; method: string; error: string | null } | null
}
