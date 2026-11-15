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
  dispatched_at?: number | null
  taken_at?: number | null
  match?: string | null
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
  /** The match zone, when the problem is at a tournament seat (issue #31). */
  match?: string | null
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

// The stats dashboard (floorbit/stats.py).
export interface StatsSample { t: number; down: number; up: number; online: number }
export interface StatsWindow { avg_bps: number; peak_bps: number; peak_at: number; online_max: number; samples: number }
export interface StatsUplink { switch_id: string; switch: string; port: string; bps: number; speed_bps: number | null; utilization: number | null }
export interface StatsTalker {
  seat: string | null
  switch_id: string
  switch: string
  port: string
  download_bps: number
  upload_bps: number
  bps: number
  nick?: string | null
}
export interface StatsData {
  monitoring: boolean
  interval: number
  last_poll: number | null
  now: (StatsSample & { ports_up: number; ports_down: number; ports_errors: number }) | null
  hour: StatsWindow | null
  day: StatsWindow | null
  peak: { bps: number; at: number } | null
  series: StatsSample[]
  uplinks: StatsUplink[]
  top: StatsTalker[]
}

// Traffic insights from NetFlow/IPFIX (floorbit/flows).
export type FlowCategory = 'gaming' | 'streaming' | 'downloads' | 'updates' | 'web' | 'other'
export type FlowMix = Partial<Record<FlowCategory, number>>
export interface FlowAnomaly {
  id: string
  kind: 'p2p' | 'burst' | 'rogue-dhcp' | 'rogue-dns'
  seat: string | null
  area: string | null
  title: string
  detail: string
  first_seen: number
  last_seen: number
}
export interface FlowsData {
  collector: boolean
  can_see_seats: boolean
  rules_error: string | null
  demo?: boolean
  stale?: boolean
  updated?: number
  flows?: number
  exporters?: { address: string; flows: number; last: number | null }[]
  mix_hour?: FlowMix
  mix_day?: FlowMix
  series?: ({ t: number } & FlowMix)[]
  areas?: { area: string; bytes: number; mix: FlowMix }[]
  services?: { name: string; category: FlowCategory; bytes: number; seats: number }[]
  other_services?: number
  seats?: { seat: string; area: string | null; bytes: number; mix: FlowMix }[] | null
  anomalies?: FlowAnomaly[]
  min_seats?: number
  retention_days?: number
  raw?: { files: number; bytes: number; oldest: string | null }
}

export interface Hall {
  id: string
  name: string
  background: string | null
  switches: number
  seat_blocks: number
}

export interface TemplateVersion {
  n: number
  saved: string
  halls: number
  switches: number
  seat_blocks: number
}

export interface LayoutTemplate {
  id: string
  name: string
  description: string
  created: string
  updated: string
  versions: TemplateVersion[]
  dropped?: string[]
}

export interface ApplyResult {
  halls: number
  seat_blocks: number
  switches_placed: number
  switches_added: number
}

export interface PlanCell {
  x: number
  y: number
  seat: string
  hit: boolean
  on: boolean | null
}

export interface PlanShape {
  cx: number
  cy: number
  rotation: number
  w: number
  h: number
  name: string
  cells: PlanCell[]
}

export interface PlanDrawing {
  shapes: PlanShape[]
  box: string
  cell: number
}

/** [time, seat, 1 online / 0 offline] */
export type SeatChange = [number, string, 0 | 1]

export interface ReplayIncident {
  id: string
  title: string
  seat: string | null
  switch: string | null
  start: number
  end: number | null
}

export interface ReplayData {
  halls: { id: string; name: string }[]
  hall: string
  drawing: PlanDrawing | null
  start: number | null
  end: number | null
  interval: number
  samples: { t: number; down: number; up: number; online: number }[]
  peak: { bps: number; at: number } | null
  seat_base: { t: number | null; online: string[] }
  seat_events: SeatChange[]
  checkins: SeatChange[]
  incidents: ReplayIncident[]
  last_poll: number | null
}

/** GET /api/report: the post-event report (issue #22). Nicks and IPs only when an admin asked. */
export interface ReportHour { t: number; online_max: number; checked_in: number; peak_bps: number; avg_bps: number }
export interface ReportOutage { switch: string; times: number; down_s: number; longest_s: number; still_down: boolean }
export interface ReportPort {
  switch: string; port: string; seat: string | null; count: number; kinds: Record<string, number>; last: number
  nick?: string | null; ip?: string | null
}
export interface ReportIncident {
  title: string; seat: string | null; switch: string | null; circuit: string | null; team: string | null
  source: string; reports: number; start: number; end: number | null; status: string
  reported_by?: string | null; assignee?: string | null; nick?: string | null; ip?: string | null
}
export interface EventReport {
  event_name: string
  start: number | null
  end: number | null
  generated: number
  people: boolean
  may_add_people: boolean
  seats: number
  online_max: number
  checked_in_max: number
  peak: { bps: number; at: number } | null
  bytes_moved: number
  hours: ReportHour[]
  outages: ReportOutage[]
  problem_ports: ReportPort[]
  incidents: { total: number; fixed: number; open: number; from_seats: number; median_fix_s: number | null; items: ReportIncident[] }
}

/** GET /api/jobs: the tech's own jobs and duty status (issue #30). Plan points are in the drawing's units. */
export interface DutyStatus { on_duty: boolean; at: string | null; since: number | null }
export interface Job {
  id: string; title: string; seat: string | null; switch_id: string | null; switch_name: string | null
  circuit_id: string | null; circuit_name: string | null; status: IncidentStatus; team: string | null
  source: string; reports: number; created_at: number; dispatched_at: number | null; taken_at: number | null
  notes: { by: string | null; at: number; text: string }[]
  drawing: PlanDrawing | null; target: [number, number] | null; from: [number, number] | null; hall: string | null
}
export interface JobsData { me: DutyStatus; seats: string[]; jobs: Job[]; can_dispatch: boolean }
export interface CrewMember { username: string; display_name: string; at: string | null; since: number | null; jobs: number }

/** Tournament awareness (issue #31). */
export interface MatchZone { id: string; name: string; blocks: string[]; seats: string[]; note: string }
export interface TournamentData {
  zones: MatchZone[]
  seats: Record<string, string>
  plans: { hall: string; name: string; drawing: PlanDrawing; match: number }[]
}
export interface QosHints {
  available: boolean
  switches: { switch: string; switch_id: string; ports: { port: string; seat: string; zone: string }[]; uplinks: string[] }[]
  missing: string[]
}

/** Shift handover (issue #33). */
export interface HandoverIncident {
  id: string; title: string; where: { kind: 'seat' | 'switch' | 'circuit'; name: string }; status: IncidentStatus
  assignee: string | null; team: string | null; created_at: number; fixed_at: number | null; match: string | null
}
export interface HandoverRecord {
  id: string; at: number; since: number; by: string | null; note: string
  counts: HandoverCounts
}
export interface HandoverCounts { open: number; opened: number; fixed: number; outages: number; still_down: number; changes: number; problems: number }
export interface HandoverData {
  since: number; now: number; previous: HandoverRecord | null
  incidents: { open: HandoverIncident[]; opened: number; fixed: HandoverIncident[] }
  outages: { switch_id: string; name: string; down_at: number; back_at: number | null; down_s: number }[]
  changes: { at: number; user: string | null; area: string; action: string; target: string | null }[]
  counts: HandoverCounts
  history: HandoverRecord[]
  discord: boolean
}

/** Build planner (issue #34). */
export interface PlannerSettings {
  model: string; access_ports: number; uplink_ports: number; spare: number
  vlan_mode: 'block' | 'hall' | 'one'; vlan_base: number; name: string
  mgmt_net: string; mgmt_first: number; mgmt_gateway: string; mgmt_vlan: number
}
export interface PlannerModel { id: string; label: string; access: string; uplink: string; builtin: boolean; text?: string }
export interface PlannedPort { n: number; name: string; seat: string; vlan: number }
export interface PlannedSwitch {
  name: string; block: string; hall_id: string; hall: string; vlan: number; mgmt_ip: string | null; exists: boolean
  ports: PlannedPort[]; spare: { n: number; name: string }[]; uplinks: { n: number; name: string }[]
}
export interface BuildPlan {
  settings: PlannerSettings; model: Omit<PlannerModel, 'builtin' | 'text'>
  blocks: { name: string; hall: string; seats: number; vlan: number; switches: string[] }[]
  switches: PlannedSwitch[]; vlans: { id: number; name: string }[]; problems: string[]
  totals: { seats: number; switches: number; new: number; vlans: number; uplinks: number }
}
export interface PlannerData { plan: BuildPlan; models: PlannerModel[] }

/** Pre-flight check board (issue #35). */
export type PreflightStatus = 'pass' | 'warn' | 'fail' | 'skip'
export type PreflightGroupId = 'switches' | 'uplinks' | 'services'
export interface PreflightItem { id: string; name: string; status: PreflightStatus; detail: string; switch_id?: string; kind?: string }
export interface PreflightGroup { at: number; by: string | null; items: PreflightItem[] }
export interface PreflightBoard {
  groups: Record<PreflightGroupId, PreflightGroup | null>
  counts: Record<PreflightStatus, number>
  ready: boolean; complete: boolean
}

/** Gear loans (issue #36). */
export interface GearLoan { to: string; kind: 'person' | 'area'; by: string | null; at: number; note: string }
export interface GearItem { id: string; name: string; role: string; model: string; serial: string; origin: string; placed: boolean; loan: GearLoan | null }
export interface GearLogEntry { device_id: string; name: string; action: 'out' | 'in'; to: string; kind: 'person' | 'area'; by: string | null; at: number; note: string; out_for?: number }
export interface GearData { items: GearItem[]; log: GearLogEntry[]; people: { username: string; display_name: string }[] }

/** Teardown checklist (issue #37). */
export interface TeardownStep { id: string; text: string; added_by: string | null; added_at: number; done_by: string | null; done_at: number | null }
export interface Teardown {
  done: boolean; left: number; total: number
  parts: {
    gear: { done: boolean; left: number; out: { id: string; name: string; to: string; at: number }[] }
    configs: { done: boolean; left: number; switches: { id: string; name: string; archived: { by: string | null; at: number } | null }[] }
    export: { done: boolean; left: number; last: { by: string | null; at: number } | null }
    custom: { done: boolean; left: number; items: TeardownStep[] }
  }
}

/** GET /api/events (issue #38): the running event and the archived ones, for comparing. */
export interface EventFigures {
  seats: number
  online_max: number
  checked_in_max: number
  peak_bps: number | null
  bytes_moved: number
  hours: number
  incidents: number
  incidents_fixed: number
  from_seats: number
  median_fix_s: number | null
  outages: number
  down_s: number
  problem_ports: number
  cache_saved_bytes: number | null
}

export interface PastEvent {
  id: string
  name: string
  start: number | null
  end: number | null
  archived_at: number
  archived_by: string | null
  figures: EventFigures
}

export interface EventsData {
  current: { name: string; start: number | null; end: number | null; figures: EventFigures }
  archived: PastEvent[]
}

/** GET /api/settings/features (issue #114). */
export interface FeatureState {
  id: string
  on: boolean
  /** What the admin chose; a feature can still be off when one it needs is. */
  chosen: boolean
  forced_off: boolean
  needs: string[]
}

// API tokens (auth/tokens.py, floorbit/blueprints/api_tokens.py)
export interface ApiToken {
  id: string
  name: string
  role: string
  role_label: string
  read_only: boolean
  created_at: number
  created_by: string | null
  expires_at: number | null
  expired: boolean
  last_used_at: number | null
}

// Outgoing webhooks (floorbit/webhooks.py)
export interface WebhookDelivery {
  at: number
  event: string
  delivery: string
  ok: boolean
  status: number | null
  error: string | null
  attempt: number
}
export interface Webhook {
  id: string
  name: string
  url: string
  events: string[]
  active: boolean
  created_at: number
  created_by: string | null
  last: WebhookDelivery | null
  deliveries: WebhookDelivery[]
}

export type DnsCategory = 'gaming' | 'streaming' | 'social' | 'updates' | 'other'
export interface DnsSite {
  site: string
  category: DnsCategory
  lookups: number
  blocked: number
  clients_max: number
  first_seen?: number
}
export interface DnsData {
  hours: { t: number; lookups: number; blocked: number }[]
  lookups: number
  blocked: number
  block_share: number | null
  sites: DnsSite[]
  categories: { id: DnsCategory; lookups: number }[]
  unnamed_lookups: number
  new: DnsSite[]
  blocked_sites: DnsSite[]
  min_clients: number
  plugins: number
  last_poll: number | null
  error: string | null
}

export interface CacheRow { cache: string; hit_bytes: number; miss_bytes: number; requests: number }
export interface LancacheData {
  configured: boolean
  demo: boolean
  hours: { t: number; hit_bytes: number; miss_bytes: number }[]
  hit_bytes: number
  miss_bytes: number
  hit_ratio: number | null
  caches: CacheRow[]
  last_read: number | null
  error: string | null
}
export interface LauncherRow {
  id: string
  name: string
  lookups: number | null
  dns_seats_max: number
  traffic_bytes: number | null
  traffic_seats: number | null
  cache_hit_bytes: number | null
  cache_miss_bytes: number | null
}
export interface GamesData {
  launchers: LauncherRow[]
  games: { name: string; bytes: number; seats: number }[]
  other_caches: CacheRow[]
  cache: LancacheData
  sources: { dns: boolean; traffic: boolean; cache: boolean }
  min_seats: { dns: number; traffic: number | null }
}

export interface ForecastPoint { t: number; bps: number; low: number; high: number; basis: 'profile' | 'recent'; pct?: number }
export interface ForecastData {
  ready: boolean
  history_hours: number
  min_hours: number
  capacity_bps: number | null
  warn_pct: number
  lead_hours: number
  points: ForecastPoint[]
  alert: { t: number; bps: number; pct: number } | null
  level: number | null
  days: number
  peak: ForecastPoint | null
}

export interface CompareSide {
  peak_bps: number | null
  avg_bps: number | null
  bytes_moved: number
  online_max: number
  hours: number
  incidents: number
  outages: number | null
}
export interface ComparePoint { hour: number; now_avg_bps: number | null; then_avg_bps: number | null; now_online: number | null; then_online: number | null }
export interface CompareData {
  day: { now: CompareSide; then: CompareSide; series: ComparePoint[]; has_then: boolean }
  event: { name: string; id: string; then_start: number; elapsed_s: number; now: CompareSide; then: CompareSide; series: ComparePoint[] } | null
}

export type LogSeverity = 'emerg' | 'alert' | 'crit' | 'err' | 'warning' | 'notice' | 'info' | 'debug'

/** One syslog line as GET /api/logs answers it (floorbit/syslog.py). */
export interface SyslogLine {
  id: number
  ts: number
  facility: number
  severity: LogSeverity
  host: string | null
  program: string | null
  message: string
  sender: string
  device: string
  port: string | null
  seat: string | null
}

export type LogSource = 'syslog' | 'app' | 'audit' | `plugin:${string}`

export interface LogStatus {
  enabled: boolean
  listening: { port: number; tcp: boolean; bind: string } | null
  error: string | null
  counts: { received: number; kept: number; not_allowed: number; rate_limited: number }
  lines: number
  devices: string[]
  retention_hours: number
  demo: boolean
  last_id: number
  sources: LogSource[]
  source: LogSource
  /** Logs plugins (Loki) that get every line, and how sending them goes. */
  stores?: { id: string; name: string; at?: number | null; sent?: number; error?: string | null }[]
  query?: string
  query_error?: string
}

export interface LogsData {
  lines: SyslogLine[]
  status: LogStatus
}

/** A saved switch command template (floorbit/commands.py, issue #94). */
export interface CommandTemplate {
  id: string
  kind: 'show' | 'change'
  label: string
  commands: string[]
  builtin: boolean
  needs_port: boolean
}

/** GET /api/commands. */
export interface CommandInfo {
  available: boolean
  plugin: string | null
  needs_login: boolean
  platform: string
  templates: CommandTemplate[]
  may_change: boolean
  may_edit: boolean
  switches: string[]
  max_switches: number
}

/** One switch's answer in POST /api/commands/run. */
export interface CommandResult {
  switch: string
  ok: boolean
  output: string
  error: string | null
  ms?: number
}

export interface CommandRun {
  template: string
  label: string
  kind: 'show' | 'change'
  port: string | null
  commands: string[]
  results: CommandResult[]
}
