// Shapes the Flask API returns. Keep in step with floorbit/plugins and auth.

/** A permission from auth/roles.py PERMISSIONS, e.g. 'floorplan.edit'. */
export type Permission = string

export interface User {
  username: string
  display_name: string
  /** admin, lead, tech, viewer, kiosk or a custom role. */
  role: string
  role_label?: string
  permissions: Permission[]
}

export interface Me {
  enabled: boolean
  user: User | null
}

export type Tone = '' | 'ok' | 'warn' | 'err'
export type State = 'up' | 'down' | 'warn' | 'unknown'

interface WidgetBase {
  id: string
  label: string
  size: 'small' | 'wide'
  refresh: number
  sub: string
  link: string
}

export type Widget = WidgetBase &
  (
    | { type: 'stat'; value: number | string; unit: string; tone: Tone }
    | { type: 'status'; items: { label: string; state: State; detail: string }[] }
    | { type: 'list'; items: { label: string; value: string; tone: Tone }[] }
    | {
        type: 'table'
        columns: { key: string; label: string }[]
        rows: Record<string, string>[]
      }
    | { type: 'sparkline'; points: number[]; value?: number; min?: number; max?: number; unit: string }
  )

export interface WidgetTile {
  kind?: undefined
  plugin: string
  plugin_name: string
  id: string
  label: string
  size: 'small' | 'wide'
  refresh: number
  url: string
}

export interface ActionTile {
  kind: 'action'
  plugin: string
  plugin_name: string
  id: string
  label: string
  danger: boolean
  url: string
}

export type Tile = WidgetTile | ActionTile

export interface ActionResult {
  ok: boolean
  message: string
  data: Record<string, unknown>
}

export interface PluginInfo {
  id: string
  name: string
  version: string
  description: string
  trust: 'builtin' | 'development' | string
  author: string
  homepage: string
  uses: { id: string; label: string }[]
  enabled: boolean
  error: string | null
  settings_section: string | null
  actions: { id: string; label: string; role: string; permission?: Permission; danger?: boolean; help?: string }[]
  widgets: { id: string; label: string; size: string; refresh: number; role: string; permission?: Permission }[]
  endpoints: { id: string; label: string; url: string }[]
  hooks: { events: string[]; action: string }[]
  has_test: boolean
}

export interface LogLine {
  time: string
  line: string
}

export const INVENTORY_FIELDS = ['name', 'role', 'model', 'serial', 'mgmt_ip', 'hall', 'status', 'notes'] as const
export type InventoryField = (typeof INVENTORY_FIELDS)[number]

export interface Device extends Record<InventoryField, string> {
  id: string
  x: number | null
  y: number | null
  placed: boolean
  origin: string
  hidden: boolean
  updated_at: string
  sources: string[]
  locked: InventoryField[]
  gone: string[]
  fed: Record<string, Partial<Record<InventoryField, string>>>
}

export interface SyncReport {
  plugin: string
  at: string
  error?: string
  received?: number
  skipped?: number
  added?: number
  updated?: number
  unchanged?: number
  joined?: number
  locked?: number
  gone?: number
  back?: number
}

export interface InventorySource {
  id: string
  name: string
  last_sync: SyncReport | null
}

export interface InventoryList {
  devices: Device[]
  sources: InventorySource[]
  roles: string[]
  fields: InventoryField[]
}

export interface ManualSeat {
  seat: string
  ip: string
  mac: string
  nick: string
  note: string
  updated_at: string | null
  updated_by: string | null
}

export interface SeatRow {
  seat: string
  ip: string
  mac: string
  nick: string
  from: Partial<Record<'ip' | 'mac' | 'nick' | 'note', string>>
  manual: ManualSeat | null
  sources: string[]
}

export interface SeatMapList {
  seats: SeatRow[]
  sources: string[]
  errors: Record<string, string>
  labels: Record<string, string>
}

export interface ImportResult {
  dry_run?: boolean
  added: number
  updated: number
  removed: number
}

// Roles and teams (auth/roles.py, auth/teams.py, auth/admin.py)
export interface RoleInfo {
  id: string
  label: string
  description: string
  permissions: Permission[]
  builtin: boolean
  users: number
}
export interface RolesList {
  permissions: { id: Permission; label: string }[]
  roles: RoleInfo[]
}
export interface TeamMember {
  username: string
  role: string
  role_label: string
}
export interface Team {
  id: string
  name: string
  parent: string | null
  depth: number
  members: TeamMember[]
}
export interface AccountSummary {
  username: string
  display_name: string
  role: string
}
export interface RoleMappingRule {
  value: string
  role: string
}
export interface OidcProvider {
  id: string
  name: string
  issuer: string
  client_id: string
  scopes: string
  role_claim: string
  role_mapping: RoleMappingRule[]
  secret_env: string
  secret_set: boolean
  callback_url: string
}
export interface OidcList {
  providers: OidcProvider[]
  roles: { id: string; label: string }[]
  callback_template: string
}
export interface OidcTestResult {
  ok: boolean
  error?: string
  problems?: string[]
  keys?: number
}
export type IncidentStatus = 'open' | 'assigned' | 'fixed'
export interface IncidentNote {
  by: string | null
  at: number
  text: string
}
export interface SeatSnapshot {
  known: boolean
  reason?: string
  switch?: string
  port?: string
  link?: string | null
  speed_bps?: number | null
  duplex?: string | null
  error_rate?: number | null
  mac_seen?: boolean
  stale?: boolean
}
export interface Incident {
  id: string
  seat: string | null
  switch_id: string | null
  switch_name?: string
  circuit_id?: string | null
  circuit_name?: string
  title: string
  problem: string | null
  team: string | null
  status: IncidentStatus
  assignee: string | null
  source: 'board' | 'helpdesk' | 'power'
  reported_by: string | null
  reports: number
  notes: IncidentNote[]
  snapshot: SeatSnapshot | null
  created_at: number
  updated_at: number
  can_work: boolean
  can_assign: boolean
}
export interface IncidentBoard {
  incidents: Incident[]
  teams: { id: string; name: string; depth: number }[]
  workable_teams: string[]
  assign_teams: string[]
  can_assign_any: boolean
  problems: string[]
}
export type IncidentPeople = Record<string, { username: string; display_name: string }[]>
export interface QrSeat {
  seat: string
  url: string
  image: string
}

// The service health wall (floorbit/health.py).
export type HealthKind = 'dhcp' | 'dns' | 'cache' | 'game' | 'uplink' | 'web' | 'other'
export interface HealthMetric {
  label: string
  value: number | string
  unit: string
  tone: Tone
}
export interface HealthCheck {
  id: string
  name: string
  kind: HealthKind
  status: State
  summary: string
  metrics: HealthMetric[]
  link: string
  plugin: string
  plugin_name: string
  since: number
}
export interface HealthWall {
  checks: HealthCheck[]
  counts: Record<State, number>
  last_poll: number | null
  interval: number
  plugins: number
}

// Security findings (floorbit/security.py) and the ports Floorbit shut (floorbit/ports.py).
export type FindingKind = 'rogue-dhcp' | 'arp-spoof' | 'mac-flap' | 'loop' | 'storm' | 'other'
export type Severity = 'high' | 'medium' | 'low'
export interface Finding {
  id: string
  plugin: string
  plugin_name: string
  kind: FindingKind
  severity: Severity
  title: string
  detail: string
  switch: string
  port: string
  seat: string
  mac: string
  ip: string
  evidence: string[]
  first_seen: number
  last_seen: number
  ack: { by: string | null; at: number } | null
  cleared_at?: number
}
export interface ShutPort {
  switch: string
  port: string
  seat: string | null
  by: string
  at: number
  reason: string
}
export interface SecurityList {
  findings: Finding[]
  cleared: Finding[]
  shut_ports: ShutPort[]
  last_poll: number | null
  interval: number
  plugins: number
  can_act: boolean
  needs_login: boolean
}

// Electrics: boards, circuits and their load (floorbit/power.py).
export type PowerState = 'ok' | 'warn' | 'crit' | 'tripped' | 'unknown'
export type Phase = 'L1' | 'L2' | 'L3' | '3P'
export interface PowerBoard {
  id: string
  name: string
  location: string
  x: number | null
  y: number | null
}
export interface PowerReading {
  amps: number
  at: number
  source: 'manual' | 'plugin'
  by?: string | null
  plugin?: string
}
export interface CircuitFeed {
  block: string
  rows: number[]
}
export interface Circuit {
  id: string
  board: string
  name: string
  phase: Phase
  rating_a: number
  meter: string
  blocks: CircuitFeed[]
  switches: string[]
  tripped: { by: string | null; at: number } | null
  reading: PowerReading | null
  state: PowerState
  load_pct: number | null
  fed: { seats: string[]; switches: { id: string; name: string }[] }
  feeds_label: string
}
export interface PowerOverview {
  enabled: boolean
  boards: PowerBoard[]
  circuits: Circuit[]
  counts: Record<PowerState, number>
  warn: number
  crit: number
  last_poll: number | null
  plugins: number
  blocks: { id: string; name: string; rows: number }[]
  can_edit: boolean
  can_read: boolean
}

// Everything wrong right now, and muted switches (floorbit/problems.py).
export type ProblemKind = 'monitoring' | 'switch' | 'health' | 'security' | 'power'
  | 'flapping' | 'errors' | 'duplex' | 'checkin'   // ports that need a look (issue #15)
export interface AlertMute {
  switch_id: string
  name: string
  until: number
  at: number
  by: string | null
  reason: string
}
export interface Problem {
  id: string
  kind: ProblemKind
  level: 'down' | 'warn'
  title: string
  where: string
  since: number | null
  link: string
  switch_id?: string
  muted?: { until: number; by: string | null; reason: string } | null
}
export interface ProblemList {
  problems: Problem[]
  attention?: Problem[]
  counts: { down: number; warn: number; muted: number; attention?: number }
  mutes: AlertMute[]
  quiet_hours: boolean
  checked_at: number
  can_mute: boolean
}
export type SetupStep = 'netbox' | 'librenms' | 'switches' | 'theme'
export interface SetupState {
  needs_account: boolean
  done: boolean
  can_set_up?: boolean
  steps?: Partial<Record<SetupStep, 'done' | 'skipped'>>
  netbox?: boolean
  librenms?: boolean
  switches?: { total: number; placed: number }
  theme?: string
}
export interface ConnectionTest {
  ok: boolean
  message: string
}
