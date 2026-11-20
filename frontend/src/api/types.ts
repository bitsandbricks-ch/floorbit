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
  /** A platform admin visiting this tenant, with no account here (floorbit/tenant_switch.py). */
  platform?: boolean
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
    /** ``min`` and ``max`` let a stat show as a gauge. ``text`` never comes from the server: a
     *  pane's value mapping sets it to show instead of the number (widgets/kinds/display.ts). */
    | { type: 'stat'; value: number | string; unit: string; tone: Tone; min?: number; max?: number; text?: string }
    | { type: 'status'; items: { label: string; state: State; detail: string; device?: string }[] }
    /** ``number`` (and ``max``) on items let a list show as bars or a pie. */
    | { type: 'list'; items: { label: string; value: string; tone: Tone; number?: number; max?: number; colour?: string; device?: string }[] }
    | {
        type: 'table'
        columns: { key: string; label: string }[]
        rows: Record<string, string>[]
      }
    | { type: 'sparkline'; points: number[]; value?: number; min?: number; max?: number; unit: string }
    /** Up to four lines of [unix seconds, value], oldest first. */
    | { type: 'series'; series: { label: string; points: [number, number][]; colour?: string; ghost?: boolean }[]; unit: string
      /** What happened when, drawn as lines across the graph. */
      marks?: { t: number; label: string; tone: Tone }[] }
  )

/** A plugin's box in a side panel (GET /api/plugins/panels?on=...). */
export interface PluginPanelInfo {
  plugin: string
  plugin_name: string
  icon: string
  id: string
  label: string
  refresh: number
  url: string
}

/** A plugin's floor plan layer (GET /api/plugins/layers). */
export interface PluginLayerInfo {
  plugin: string
  plugin_name: string
  icon: string
  id: string
  label: string
  refresh: number
  url: string
}

/** One plugin page (GET /api/plugins/<id>/pages/<page>): its tiles this account may see. */
export interface PluginPageData {
  plugin: string
  plugin_name: string
  icon: string
  id: string
  label: string
  columns: number
  tiles: Tile[]
}

export type PluginLayerTone = 'ok' | 'warn' | 'err' | 'info'

/** What one plugin layer draws (GET /api/plugins/<id>/layers/<layer>). */
export interface PluginLayerData {
  seats: Record<string, { tone: PluginLayerTone; label: string }>
  legend: { tone: PluginLayerTone; label: string }[]
}

export interface WidgetTile {
  kind?: undefined
  plugin: string
  plugin_name: string
  id: string
  label: string
  size: 'small' | 'wide'
  refresh: number
  url: string
  /** A pane may pick the time it shows (``?range=``) and compare it (``?compare=``), issue #960. */
  ranges?: boolean
  /** It can mark what happened on its graph (``?marks=1``): switches down, incidents. */
  marks?: boolean
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
  icon?: string
  version: string
  description: string
  trust: 'builtin' | 'development' | 'official' | string
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
  /** ``schema:`` of this version, and the schema this tenant's data is at (0: none). */
  schema?: number
  data_schema?: number
}

export interface LogLine {
  time: string
  line: string
}

export const INVENTORY_FIELDS = ['name', 'role', 'model', 'serial', 'mgmt_ip', 'hall', 'status', 'notes',
  'platform', 'os', 'cpu', 'cores', 'memory_mb', 'disk_gb', 'host', 'location'] as const
export type InventoryField = (typeof INVENTORY_FIELDS)[number]
export const SPEC_FIELDS = ['platform', 'os', 'cpu', 'cores', 'memory_mb', 'disk_gb', 'host'] as const

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
  icon?: string
  color?: string
  group_id?: string | null
  tags?: string[]
  properties?: Record<string, string>
  features?: Record<string, boolean>
  /** Values of the fields the Device type has (inventory types). */
  fields?: Record<string, string>
  interface_count?: number
  blocked?: number
  /** Live, in the list only: the status monitor's state (null before it polled) and ports up of all. */
  state?: 'online' | 'offline' | 'unknown' | null
  ports?: { up: number; total: number } | null
  drift?: number
}

/** Icon, colour, tags, properties and feature switches: what devices, groups and tags all carry. */
export interface ScopeHolder {
  id: string
  name: string
  icon: string
  color: string
  properties: Record<string, string>
  features: Record<string, boolean>
}

export interface InventoryGroup extends ScopeHolder {
  parent_id: string | null
  tags: string[]
  notes: string
  devices: number
  credentials: string[]
}

export interface InventoryTag extends ScopeHolder {
  description: string
  used: number
  credentials: string[]
}

export interface FeatureInfo {
  id: string
  core: boolean
  name: string
  default: boolean
  agent?: boolean
}

/** An SVG from the shared icon library (floorbit/icon_library.py); `id` starts with `custom-`. */
export interface CustomIcon { id: string; name: string; url: string; by: string; at: number | null }

/** A field an admin set up on an inventory type (floorbit/inventory_types.py). */
export interface FieldDef {
  key: string; label: string; kind: 'text' | 'number' | 'choice' | 'bool' | 'link'
  choices: string[]; default: string; link: string
}
export interface InventoryType {
  id: string; name: string; sort: 'device' | 'linked' | 'stored'; builtin: boolean
  icon: string; default_icon: string; color: string
  /** Built-in fields first, then the ones set up here (`own_fields`). */
  fields: FieldDef[]; own_fields: FieldDef[]
  properties: Record<string, string>; features: Record<string, boolean>; count: number
}
export interface InventoryEntry {
  id: string; type: string; name: string; summary: string; detail: string; link: string
  group_id: string | null; tags: string[]; properties: Record<string, string>
  icon: string; color: string; notes: string; fields: Record<string, string>
  /** Stored entries a plugin feeds (NetBox): which, and which no longer send it. */
  sources?: string[]; gone?: string[]; locked?: string[]
}
export interface EntryDetail extends InventoryEntry {
  resolved: Omit<DeviceDetail['resolved'], 'credentials' | 'features'>
  field_values: (FieldDef & { value: string; is_default: boolean })[]
}

export interface InventoryOverview {
  groups: InventoryGroup[]
  tags: InventoryTag[]
  defaults: { properties: Record<string, string>; features: Record<string, boolean>; credentials: string[] }
  features: FeatureInfo[]
  icons: string[]
  custom_icons?: CustomIcon[]
  credential_kinds: string[]
  auth_protocols: string[]
  priv_protocols: string[]
  ungrouped: number
}

export const INTERFACE_FIELDS = ['type', 'speed_mbps', 'mac', 'ips', 'vlan', 'mode', 'description', 'enabled', 'mgmt', 'lag'] as const
export type InterfaceField = (typeof INTERFACE_FIELDS)[number]

export interface DeviceInterface {
  id: string
  name: string
  type: string
  speed_mbps: number | null
  mac: string
  ips: string[]
  vlan: number | null
  mode: string
  description: string
  enabled: boolean
  mgmt: boolean
  lag: string
  origin: string
  hidden: boolean
  sources: string[]
  locked: InterfaceField[]
  gone: string[]
  fed: Record<string, Partial<Record<InterfaceField, unknown>>>
}

export interface Origin {
  type: 'device' | 'tag' | 'group' | 'type' | 'defaults'
  id: string
  name: string
}

export interface CredentialInfo {
  id: string
  kind: string
  owner_type: string
  owner_id: string
  owner_name?: string
  username: string
  auth_protocol: string
  priv_protocol: string
  rev: string
  set_at: number | null
  set_by: string | null
  secrets: string[]
}

export interface LoginBlock {
  credential_id: string
  rev: string
  kind: string
  plugin: string
  message: string
  agent: string | null
  at: number
  device_id: string
  device: string
}

export interface DeviceDetail extends Device {
  interfaces: DeviceInterface[]
  own_credentials: CredentialInfo[]
  blocks: LoginBlock[]
  /** What goes down with this device: VMs on it, and game servers on it or on those VMs. */
  runs_here?: { kind: 'device' | 'game-server'; id: string; name: string; role?: string; via?: string }[]
  /** What is wired to it: cables on its ports, circuits that feed it, internet lines on it. */
  connected?: {
    cables: { id: string; label: string; port: string; panel: string; panel_port: string; seat: string; type: string; speed: number | null }[]
    circuits: { id: string; name: string; board: string; phase: string; rating_a: number | null }[]
    uplinks: { id: string; name: string; port: string; capacity_mbps: number | null }[]
    /** Entries whose device field names it: the optics in its ports, ... */
    entries?: { id: string; type: string; name: string; port: string }[]
  }
  resolved: {
    properties: Record<string, { value: string; from: Origin }>
    features: Record<string, { on: boolean; from: Origin | null }>
    tags: { id: string; name: string; color: string; icon: string; own: boolean }[]
    look: { icon: { value: string; from: Origin | null }; color: { value: string; from: Origin | null } }
    credentials: Record<string, CredentialInfo & { from: Origin; blocked: boolean }>
    group_path: { id: string; name: string }[]
  }
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
  every?: number
  roles: string[]
  fields: InventoryField[]
}

export interface ManualSeat {
  seat: string
  switch: string
  port: string
  ip: string
  mac: string
  nick: string
  note: string
  updated_at: string | null
  updated_by: string | null
}

export interface SeatRow {
  seat: string
  /** The key: the switch port the seat is on. IP and MAC are read off it. */
  switch: string
  port: string
  /** Where the port came from: typed in, a cable, or a check-in. */
  port_origin: '' | 'manual' | 'cable' | 'checkin'
  ip: string
  mac: string
  nick: string
  from: Partial<Record<'switch' | 'port' | 'ip' | 'mac' | 'nick' | 'note', string>>
  manual: ManualSeat | null
  sources: string[]
  /** On a seat block of any hall; off-plan rows come only from a source (seats.json, a CSV feed). */
  on_plan: boolean
}

export interface SeatMapList {
  seats: SeatRow[]
  sources: string[]
  errors: Record<string, string>
  labels: Record<string, string>
}

export interface FoundPort {
  switch: string
  port: string
  ip: string
  mac: string
  held_by: string | null
}

export interface ResolvePortsResult {
  dry_run: boolean
  found: Record<string, { switch: string; port: string }>
  missed: string[]
  taken: { seat: string; held_by: string; switch: string; port: string }[]
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

/** An account on Settings > Users (auth/users.py ``public``): no secrets. */
export interface Account extends AccountSummary {
  role_label: string
  has_password: boolean
  /** Linked sign-ins: "discord" or "oidc:<provider>". */
  identities: string[]
  discord_id: string
  created_by: string | null
  /** The dashboards this account is limited to (a wall screen, #702); empty: every one. */
  dashboards: string[]
  /** Runs the platform: a flagged admin of the default tenant (docs/tenancy.md). */
  platform_admin?: boolean
}

export interface AccountsList {
  users: Account[]
  /** Whoever looks is a platform admin, so may give and take the flag. */
  platform?: boolean
  roles: { id: string; label: string; description: string }[]
  me: string | null
  discord: boolean
  oidc: { id: string; label: string }[]
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
/** Speed test at the seat (issue #99): Mbit/s and ms, nothing personal. */
export interface SpeedtestResult { down_mbps: number | null; up_mbps: number | null; ping_ms: number | null; jitter_ms: number | null; at: number }

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
  source: 'board' | 'helpdesk' | 'power' | 'discord'
  reported_by: string | null
  reports: number
  notes: IncidentNote[]
  snapshot: SeatSnapshot | null
  /** The latest speed test from the seat's help page (issue #99). */
  speedtest?: SpeedtestResult | null
  created_at: number
  updated_at: number
  /** When it was marked fixed; null while not fixed. */
  fixed_at?: number | null
  dispatched_at?: number | null
  taken_at?: number | null
  /** The attendee said on the help page that it works again (issue #372); the crew still decides. */
  seat_ok_at?: number | null
  /** The seat's switch is down right now (issue #386). */
  outage?: { switch: string; since: number } | null
  /** Filed while the seat's switch was down, and the switch is back since (issue #390). */
  back_up?: { switch: string; since: number } | null
  can_work: boolean
  can_assign: boolean
  /** The seat's crew note (issue #204). */
  seat_note?: { text: string; by: string | null; at: number } | null
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
  /** With check-in on: the PIN printed on this seat's card, which names the seat. */
  pin?: string | null
}

// The service health wall (floorbit/health.py).
export type HealthKind = 'dhcp' | 'dns' | 'cache' | 'game' | 'uplink' | 'firewall' | 'web' | 'other'
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
  /** Until when its alerts are muted (issue #260), or null. */
  muted_until?: number | null
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
  /** label: the name, or the row letters of a block named by its rows; row_names: each row, top first. */
  blocks: { id: string; name: string; label: string; rows: number; row_names: string[] }[]
  can_edit: boolean
  can_read: boolean
}

// Everything wrong right now, and muted switches (floorbit/problems.py).
export type ProblemKind = 'monitoring' | 'switch' | 'health' | 'security' | 'power' | 'link' | 'wifi' | 'plugin'
  | 'flapping' | 'errors' | 'duplex' | 'checkin'   // ports that need a look (issue #15)
export interface AlertMute {
  /** The switch id, ``health:<service id>`` for a service (issue #256) or ``wifi:<ap>`` for an access point. */
  switch_id: string
  kind?: 'switch' | 'health' | 'wifi'
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
  /** The mute key: switches, services and Wi-Fi access points. */
  mute_id?: string
  name?: string
  muted?: { until: number; by: string | null; reason: string } | null
  /** An offline switch's open incident, for people who see the board (issue #278). */
  incident?: string | null
  /** What a down switch or link cuts off (issue #950): seat names only, and the switches behind it. */
  seats?: string[]
  behind?: string[]
  /** The down switch this one is behind: the place to start. */
  cause?: string
}
export interface ProblemList {
  problems: Problem[]
  attention?: Problem[]
  counts: { down: number; warn: number; muted: number; attention?: number }
  mutes: AlertMute[]
  quiet_hours: boolean
  checked_at: number
  can_mute: boolean
  can_report?: boolean
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
  /** The local agent whose collector sent this summary (issue #2). */
  agent?: string
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
  /** Where the background sits (drawing units on the plan, % on a hall) and how see-through it is. */
  background_frame?: { x: number; y: number; w: number; h: number } | null
  background_opacity?: number | null
  /** Metres per seat (one grid cell), from calibrating; null when not known. */
  seat_m?: number | null
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
  /** Row and column (from 0) in the block, for the editor's seat handles; missing on older answers. */
  rc?: [number, number]
}

export interface PlanShape {
  /** The seat block's id, for the editor; missing on older answers. */
  id?: string
  cx: number
  cy: number
  rotation: number
  w: number
  h: number
  name: string
  cells: PlanCell[]
  /** Row letters (blocks named by row), in the block's own coordinates; missing on older answers. */
  rows?: { text: string; x: number; y: number }[]
  /** Each row, top first (a cell's rc[0]): its id and name as /api/options/rows has them. Ids are
   *  the server's: never build one. Missing on older answers. */
  row_list?: { id: string; name: string }[]
  /** The seats stand where the editor put them, not in rows (floorbit/seat_layout.py). */
  free?: boolean
}

/** Text, walls, zones and icons on a hall (floorbit/plan_marks.py), in drawing units. */
/** Items of one hall the editor moves as one (floorbit/plan_groups.py). */
export interface PlanGroup {
  id: string
  hall_id?: string
  name: string
  members: { kind: 'block' | 'mark' | 'switch' | 'panel' | 'board'; id: string }[]
}

export interface PlanMark {
  id?: string
  kind: 'text' | 'icon' | 'wall' | 'zone'
  /** Drawing order, higher on top (floorbit/stacking.py). */
  z?: number
  x: number
  y: number
  text?: string
  icon?: string
  size?: 's' | 'm' | 'l'
  /** Stretch on top of ``size`` for a label or icon (0.25 to 8; missing is 1). */
  scale?: number
  rotation?: number
  x2?: number
  y2?: number
  /** A wall's bends between its ends, [x, y] each (drawing units in the plan, % from /api/plan-marks). */
  points?: [number, number][]
  style?: 'solid' | 'dashed'
  w?: number
  h?: number
  label?: string
  color?: 'muted' | 'bit' | 'trace' | 'warn' | 'down'
  /** The floor plan layer it's on (floorbit/plan_marks.py LAYERS); overview when missing. */
  layer?: 'overview' | 'safety' | 'network' | 'electrical' | 'services'
  /** The crew's own colour, ``#rrggbb``; missing is the theme's. */
  tint?: string
}

export interface PlanDrawing {
  shapes: PlanShape[]
  box: string
  cell: number
  marks?: PlanMark[]
  /** The path data of the icons the marks use, by name (24 x 24, stroked). */
  icons?: Record<string, string[]>
  /** Uploaded icons the marks use, by id, as ``data:`` URIs (floorbit/icon_library.py). */
  custom_icons?: Record<string, string>
}

/** GET /api/report: the post-event report (issue #22). Nicks and IPs only when an admin asked. */
export interface ReportHour { t: number; online_max: number; checked_in: number; peak_bps: number; avg_bps: number; incidents?: number }
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
  incidents: { total: number; fixed: number; open: number; from_seats: number; median_fix_s: number | null; median_take_s?: number | null; repeat_seats?: { seat: string; count: number }[]; seat_problems?: { problem: string; count: number }[]; items: ReportIncident[] }
}

/** GET /api/jobs: the tech's own jobs and duty status (issue #30). Plan points are in the drawing's units. */
export interface DutyStatus { on_duty: boolean; at: string | null; since: number | null }
export interface Job {
  id: string; title: string; seat: string | null; switch_id: string | null; switch_name: string | null
  circuit_id: string | null; circuit_name: string | null; status: IncidentStatus; team: string | null
  source: string; reports: number; created_at: number; dispatched_at: number | null; taken_at: number | null
  notes: { by: string | null; at: number; text: string }[]
  /** The attendee tapped "It works again" on the seat's help page (issue #382). */
  seat_ok_at?: number | null
  drawing: PlanDrawing | null; target: [number, number] | null; from: [number, number] | null; hall: string | null
  /** The steps for this kind of incident, right on the job (issue #102). */
}
export interface JobsData { me: DutyStatus; seats: string[]; jobs: Job[]; can_dispatch: boolean; done?: number; auto?: boolean }
export interface CrewMember { username: string; display_name: string; at: string | null; since: number | null; jobs: number; done?: number }

/** Shift handover (issue #33). */
export interface HandoverIncident {
  id: string; title: string; where: { kind: 'seat' | 'switch' | 'circuit'; name: string }; status: IncidentStatus
  assignee: string | null; team: string | null; created_at: number; fixed_at: number | null
}
export interface HandoverRecord {
  id: string; at: number; since: number; by: string | null; note: string
  counts: HandoverCounts
}
export interface HandoverCounts { open: number; waiting?: number; opened: number; fixed: number; outages: number; still_down: number; changes: number; problems: number; muted?: number; median_fix_s?: number | null }
export interface HandoverData {
  since: number; now: number; previous: HandoverRecord | null
  incidents: { open: HandoverIncident[]; opened: number; fixed: HandoverIncident[] }
  outages: { switch_id: string; name: string; down_at: number; back_at: number | null; down_s: number }[]
  changes: { at: number; user: string | null; area: string; action: string; target: string | null }[]
  /** Crew notes on seats written or changed this shift (issue #202). */
  seat_notes: { seat: string; text: string; by: string | null; at: number }[]
  /** What is muted right now, and the crew notice that is up (issue #258). */
  mutes?: { kind: 'switch' | 'health'; name: string; until: number; by: string | null; reason: string }[]
  notice?: CrewNotice | null
  coming_up?: { id: string; title: string; kind: string; start: number; end: number | null; where: string | null }[]
  counts: HandoverCounts
  history: HandoverRecord[]
  discord: boolean
}

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
  /** From reported to first taken by someone (issue #294); null for events archived before it. */
  median_take_s: number | null
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
/** One audit log line (floorbit/audit.py): names what changed, never the values. */
export interface AuditEntry {
  time: string
  user: string | null
  area: string
  action: string
  target?: string
  fields?: string[]
  ok?: boolean
}

export interface AuditPage {
  entries: AuditEntry[]
  total: number
  areas: string[]
}

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
/** One agent's view of the LAN cache machine (the lancache agent plugin's status). */
export interface LancacheAgent {
  id: string
  name: string | null
  updated: number | null
  stale: boolean
  disk: { used?: number; total?: number; free?: number; error?: string } | null
  heartbeat: { ok: boolean; ms?: number; processed_by?: string; error?: string } | null
  dns_check: { ok: boolean; error?: string } | null
  clearing: { running: boolean; started: number; finished?: number; removed: number; errors: number } | null
  health: AgentPluginHealth | null
}
export interface LancacheDownload extends CacheRow { item: string; clients: number; hit_ratio: number | null }
export interface LancacheOverview extends LancacheData {
  plugin_on: boolean
  /** False when the plugin is not installed from the Marketplace. */
  plugin_installed?: boolean
  agents: LancacheAgent[]
  downloads: LancacheDownload[]
  other_downloads: { hit_bytes: number; miss_bytes: number; requests: number; items: number }
  suspects: { cache: string; item: string; files: number; misses: number }[]
  dns_services: { cache: string; lookups: number }[]
  clients: { t: number; clients: number }[]
  min_clients: number
  window_hours: number
  saved_bytes: number
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
  /** Local agents that send the event network's syslog on (issue #2). */
  relayed?: { agent: string; at: number; lines: number; dropped: number; recent: boolean }[]
  sources: LogSource[]
  source: LogSource
  /** Logs plugins (Loki) that get every line, and how sending them goes. */
  stores?: { id: string; name: string; at?: number | null; sent?: number; error?: string | null }[]
  /** DHCP lease lines read from the syslog: a fresh IP to MAC source (docs/syslog.md). */
  leases?: { granted: number; released: number; last_at: number | null }
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

/** GET /api/terminal (floorbit/terminal.py, issue #95). */
export interface TerminalInfo {
  available: boolean
  plugin: string | null
  needs_login: boolean
  switches: string[]
  sessions: { id: string; switch: string; opened: number }[]
  idle_minutes: number
  max_minutes: number
}

/** GET /api/terminal/<id>/output. */
export interface TerminalOutput {
  data: string
  next: number
  skipped: number
  closed: string | null
}

/** Cables and patching (issue #97). */
export interface Cable {
  id: string; label: string; switch: string; port: string; panel: string; panel_port: string; seat: string
  color: string; length_m: number | null; note: string; source: 'floorbit' | 'import'; plugin?: string
  /** Cable type and speed (issue #468), like the links between switches. */
  type?: LinkType | ''; speed?: number | null
  updated_at: number; by: string | null; block?: string
}
export interface CableList { cables: Cable[]; sources: string[] }
export interface CableImport { imported: number; errors: string[] }
/** A seat block patched to a switch in one go (issue #473). */
export interface PlannedCable { seat: string; switch: string; port: string; block: string }
export interface CableClash {
  seat: string; port: string; kind: 'port' | 'seat'; cable: string; imported: boolean
  other_seat?: string; other_port?: string
}
export interface BlockPlan { rows: string[]; cables: PlannedCable[]; clashes: CableClash[]; created?: number; removed?: number }
export interface PatchRow { switch: string; port: string; seat?: string; cable?: string; state?: string; described_seat?: string }
export interface PatchList { count: number; rows: PatchRow[] }
export interface PatchCheck {
  /** Each hall row's cabled seats and how many are up (#1057). */
  last_poll: number | null; rows: { row: string; name: string; block_label: string; naming: string; seats: number; up: number }[]
  missing: PatchList; down: PatchList; unplanned: PatchList; conflicts: PatchList; unread: string[]
}
/** Clients on seat ports the patch plan doesn't explain (issue #473), from MAC tables and ARP. */
/** The rough area a port goes to (floorbit/port_areas.py). */
export interface PortAreaHint { label: string; seats: string[] }
export interface PortArea { id: string; switch: string; first: number; last: number; seats: string[]; label: string; updated_at?: number; by?: string | null }
export interface PortClient { switch: string; port: string; mac: string; ip: string; ip_seat: string; seat?: string; cable?: string; area?: PortAreaHint | null }
export interface PortClients {
  as_of: number | null; reading: boolean; started: boolean; error: string | null; switches: number; clients: number
  failed: { switch: string; error: string }[]
  unplanned: { count: number; rows: PortClient[] }; moved: { count: number; rows: PortClient[] }
  /** Seat ports with more than one machine (issue #1119): only how many, never which. */
  shared?: { count: number; rows: SharedPort[] }
  /** Issue #949: IPs ARP knows on no seat port, and cabled seats with no machine (once check-ins started). */
  no_port?: { count: number; rows: { mac: string; ip: string; ip_seat: string }[] }
  empty?: { count: number; rows: { seat: string; switch: string; port: string }[] }
  ignored?: number
}
export interface SharedPort { switch: string; port: string; seat: string; cable: string; macs: number; desk_switch: boolean }
/** Walking the row (issue #473): ports that came up since the walk began. */
export interface WalkUp { port: string; at: number; how: 'syslog' | 'poll'; area?: PortAreaHint | null }
export interface WalkWatch { ups: WalkUp[]; syslog: boolean; since: number }
/** The crew's walk-through check-in (floorbit/seat_walk.py). */
export interface WalkPort { switch: string; port: string; learned_at?: number; source?: 'walk' | 'checkin' }
export interface SeatWalkInfo {
  /** Where laptops in the hall reach the local agent, which identifies them (null: not known). */
  agent_url: string | null; through_agent?: boolean; switch_lookup: boolean; monitoring: boolean; keep_hours: number
  event: { id: string; name: string; status: string }
  rows?: string[]; row_names?: string[]; seats?: { seat: string; port: WalkPort | null }[]
  /** Every hall row: how far the walk got and who walks it now (#1000). */
  hall?: WalkHallRow[]
}
export interface WalkHallRow {
  id: string; name: string; block_label: string; naming: string; seats: number; found: number
  walker: { id: string; who: string; seat: string | null } | null
}
export interface SeatWalker { id: string; who: string; rows: string[]; seat: string | null }
/** ip: the page came through an agent, the laptop is known at once; else url: the agent to open once. */
export interface SeatWalkHello { hello: string; url?: string; ip?: string }
export interface SeatLocated {
  ok: boolean; retry: boolean; seat: string; ip: string | null; mac: string | null; how: 'switch' | 'snmp' | 'monitoring' | null
  ms: number; tries: number; stale: boolean; found: WalkPort | null
  steps: { step: 'mac' | 'switch' | 'snmp' | 'monitoring'; ok: boolean; how?: string | null }[]
  replaced?: string[]; plan_seat?: string | null
}
export interface SeatAssigned { cable: Cable; changed: string[]; other_seat: string }
/** A switch login Floorbit keeps (issue #474): never the password. */
/** label: what pickers show: the name, or the row letters (C–D) of a block named by its rows. */
export interface SeatBlock { id: string; name: string; label: string; row_names: string[]; cols: number; rows: number; hall_id: string }

/** Wi-Fi view (issue #98). Client counts only. */
export type WifiBand = '2.4' | '5' | '6'
export interface WifiRadio { band: WifiBand; channel: number | null; width: number | null; utilization: number | null; clients: number }
export interface WifiAp {
  name: string; model: string; status: 'up' | 'down'; clients: number; radios: WifiRadio[]; source: string
  placed: boolean; on_plan: boolean; px: number | null; py: number | null; busy: boolean
}
export interface WifiData {
  aps: WifiAp[]; clients: number; up: number; down: string[]; busy: string[]
  overlaps: { band: WifiBand; channel: number; aps: [string, string] }[]
  bands: Partial<Record<WifiBand, { clients: number; radios: number; utilization: number | null }>>
  sources: string[]; errors: string[]; thresholds: { busy: number; crowded: number }
  drawing: PlanDrawing | null; hall: string; halls: { id: string; name: string }[]
  /** A controller streams to Telemetry, so clients over time are kept (GET /api/wifi/history). */
  history?: boolean
}

/** Open incidents per seat and per switch id (GET /api/incidents/markers), for the crew layer. */
export interface IncidentMarkers { seats: Record<string, number>; switches: Record<string, number> }

/** Event changelog (issue #100). */
export type TimelineKind = 'change' | 'sign-in' | 'outage' | 'incident' | 'alert' | 'deploy'
export interface TimelineEntry {
  t: number; kind: TimelineKind; title: string; target?: string; who?: string; area?: string
  /** What a change touched, as stored (setting keys for settings): see lib/auditFields.ts. */
  fields?: string[]
  severity?: 'up' | 'down' | 'warn' | 'info'; version?: string; id?: string
}
export interface TimelineData { entries: TimelineEntry[]; total: number; counts: Record<TimelineKind, number>; kinds: TimelineKind[]; more: boolean }

/** The public network status page (issue #101), as GET /api/status-page gives it. */
export type StatusState = 'operational' | 'degraded' | 'outage' | 'maintenance' | 'unknown'

export interface StatusArea {
  hall: string
  block: string
  /** Row numbers, for example "1-3, 5". Empty when Floorbit only knows the nearest block. */
  rows: string
  seats: number | null
  switches?: string[]
}

export interface StatusUpdate {
  id: string
  at: number
  text: string
  state: StatusState | null
  area: string
}

/** One count of every service (issue #1037): the health wall's checks, each internet site a row. */
export interface ServiceSummaryRow {
  id: string; name: string; kind: string; status: ServiceStatus; summary: string; link: string
}
export interface ServiceSummary {
  rows: ServiceSummaryRow[]
  total: number
  counts: Record<ServiceStatus, number>
  by_kind: Record<string, Record<ServiceStatus | 'total', number>>
}

export interface StatusPageData {
  state: StatusState
  auto_state: StatusState
  override: { state: StatusState; note: string; by: string | null; at: number } | null
  since: number | null
  /** What players notice (issue #1038): switches, firewall, no_firewall, internet_slow, internet_down, dns, dhcp. */
  reasons?: string[]
  areas: StatusArea[]
  crew_areas: StatusArea[]
  /** Areas whose switch came back in the last half hour, with switch names (issue #396). */
  recovered: StatusArea[]
  recovered_at: number | null
  crew_recovered: StatusArea[]
  updates: StatusUpdate[]
  checked_at: number
  /** Is /status switched on (Settings > Public)? */
  public: boolean
}

/** One frame of the whole-event recording (issue #104). blocks: name -> [seats, online, bps, open incidents]. */
export interface EventFrame {
  t: number
  down: number
  up: number
  online: number
  seats: string[]
  incidents: string[]
  blocks: Record<string, [number, number, number, number]>
}

/** GET /api/replay/event: the whole event of one hall, a frame every 5 minutes, thinned out as it ages. */
export interface EventReplayData {
  halls: { id: string; name: string }[]
  hall: string
  drawing: PlanDrawing | null
  frames: EventFrame[]
  start: number | null
  end: number | null
  step: number
}

/** The event schedule (issue #106): talks, tournaments, meals and quiet hours. */
export type ScheduleKind = 'talk' | 'tournament' | 'meal' | 'quiet' | 'other'
export interface ScheduleItem {
  id: string
  title: string
  kind: ScheduleKind
  start: number
  end: number | null
  where: string
  note: string
  source: 'floorbit' | 'ical'
  uid: string | null
  updated_at: number | null
  by: string | null
}
export interface ScheduleData {
  event: { start: number | null; end: number | null }
  items: ScheduleItem[]
  kinds: ScheduleKind[]
}

/** GET /api/plan (issue #55): every seat with one state, for the floor plan view. No nicks or IPs. */
export type SeatState = 'online' | 'offline' | 'unknown'

export interface PlanSeat {
  state: SeatState
  checked_in?: boolean
  taken?: boolean
  problems?: number
  bps?: number
  /** When the link last changed, if within the last 15 minutes (issue #171). */
  changed?: number
  /** The crew left a note on the seat (issue #180); its text is in SeatDetails. */
  note?: boolean
  /** The down switch or link that cuts the seat off (issue #950); crew only. */
  behind?: string
}

export interface PlanBlock {
  name: string
  seats: number
  online: number
  problems: number
}

export interface PlanSwitch {
  id: string
  name: string
  status: string
  /** Added by hand on the plan (deleting removes it), not from the inventory (deleting unplaces it). */
  manual?: boolean
  x: number
  y: number
}

/** A patch panel placed on this plan (drawing units), with its port count and how many have a cable. */
export interface PlanPanel { name: string; x: number; y: number; ports: number; used: number }
/** GET /api/cable-plan?hall= (floorbit/cable_plan.py): the cables to draw, points in % of the plan. */
export interface PlanCable {
  key: string; kind: 'lan' | 'uplink' | 'power'; layer: string; points: [number, number][]; manual: boolean
  /** The crew has drawn this cable (bends or corners) rather than leaving it automatic. */
  drawn?: boolean
  /** straight: one line end to end (``bends`` kept for when it is angled again). */
  corners: 'square' | 'round' | 'straight'; via: string | null; label: string; media?: string; speed?: number | null
  /** The bends the crew placed (null: automatic route). */
  bends?: [number, number][] | null
  ref: { cable?: string | null; source?: string; switch?: string; port?: string; seat?: string; link?: string; circuit?: string }
}
export interface CablePlan { cables: PlanCable[]; panels: { name: string; x: number | null; y: number | null; ports: number }[]; auto: boolean }
export interface PlanLink { id: string; a: string; b: string; type: LinkType | ''; media: string; speed: number | null; issue: '' | 'down' | 'slow' }
/** GET /api/power/markers (floorbit/power.py): the boards and each circuit's cable, for the plan's power layer. */
/** GET /api/firewalls/seats (issue #470): the seats whose traffic isn't on its planned firewall. */
export interface FirewallSeats {
  enabled: boolean
  seats: Record<string, { now: string | null; intended: string | null; state: 'failover' | 'down' }>
}

export interface PowerMarkers {
  enabled: boolean
  boards: { id: string; name: string; x: number; y: number; state: PowerState }[]
  circuits: { id: string; name: string; board: string; state: PowerState; pct: number | null; seats: string[]; switches: string[] }[]
  counts: Partial<Record<PowerState, number>>
}

export interface SeatViewData {
  /** Each hall's totals, for the hall picker (issue #196). */
  halls: { id: string; name: string; seats: number; online: number; problems: number }[]
  hall: string
  drawing: PlanDrawing | null
  size: { w: number; h: number; cell: number }
  background: string | null
  /** Where the background sits (drawing units on the plan, % on a hall) and how see-through it is. */
  background_frame?: { x: number; y: number; w: number; h: number } | null
  background_opacity?: number | null
  /** Metres per seat (one grid cell), from calibrating; null when not known. */
  seat_m?: number | null
  switches: PlanSwitch[]
  /** Links between switches placed on this plan (issue #468); older servers send none. */
  links?: PlanLink[]
  /** Patch panels placed on this plan; older servers send none. */
  panels?: PlanPanel[]
  /** Power distribution boards placed on the plan (drawing units); none with power off. */
  boards?: { id: string; name: string; x: number; y: number }[]
  seats: Record<string, PlanSeat>
  blocks: PlanBlock[]
  monitoring: boolean
  checkin: boolean
  last_read: number | null
}

/** GET /api/plan/seats/<seat>: one seat for the inspector. nick, ip and mac only with seats.view. */
export interface SeatDetails {
  seat: string
  block: string
  state: SeatState
  bps: number | null
  switch: string | null
  port: string | null
  incidents: { id: string; title: string; status: string; created_at: number }[]
  /** Incidents fixed at this seat before, and the latest one (issue #330). */
  fixed_before?: { count: number; last: { title: string; fixed_at: number | null } | null }
  attention: { kind: string; title: string; since: number }[]
  /** The link over the last hours (issue #167): online at ``from`` (null: not read yet), then each change. */
  history?: { from: number; to: number; start: boolean | null; changes: [number, number][] }
  checked_in: boolean | null
  /** Crew only: the port lookup of the seat's check-in, when it has one. */
  checkin_wired?: WiredState
  last_read: number | null
  people: boolean
  /** May this account read and write the seat's note (incidents.work)? */
  crew: boolean
  note?: SeatNote | null
  /** The player's speed tests from the help page, newest first (issue #182); crew only. */
  speedtests?: SeatSpeedTest[]
  /** Which firewall the core sends the seat to (issue #470); crew only, null when no range covers it. */
  firewall?: SeatFirewall | null
  nick?: string | null
  ip?: string | null
  mac?: string | null
}

export interface SeatFirewall { intended: string | null; now: string | null; state: FirewallRouteState; range: string }
export type FirewallRouteState = 'primary' | 'failover' | 'unknown' | 'down'

/** GET /api/firewalls (issue #470): the firewalls with their health, and each seat range's route now. */
export interface FirewallRange {
  id: string; cidr: string; name: string; firewalls: string[]; intended: string | null; now: string | null
  state: FirewallRouteState; seats: number
  /** 'import': read from NetBox (change it there); 'floorbit': planned here. */
  source?: 'import' | 'floorbit'; plugin?: string
  /** Inventory switch or group ids the range is for: their seats outside it are flagged (issue #1062). */
  switches?: string[]
}
export interface FirewallCard {
  id: string; name: string; model: string; hall: string; status: 'online' | 'offline' | 'unknown'
  serving: string[]; planned: string[]; backup_for: string[]; seats: number
}
export interface FirewallList {
  firewalls: FirewallCard[]; ranges: FirewallRange[]; unread: boolean; monitoring?: boolean; can_import?: boolean
  counts: { firewalls: number; down: number; failover: number; without: number }
}

/** GET /api/services (issue #471): ISP uplinks, DNS resolvers, internet sites and the LAN cache. */
export type ServiceStatus = 'up' | 'warn' | 'down' | 'unknown'
interface ServiceState { status: ServiceStatus; since: number | null; checked_at: number | null; history: [number, number | null][]; error: string }
export interface IspUplink extends ServiceState {
  id: string; name: string; device: string; port: string; capacity_mbps: number; probe_host: string; probe_port: number
  port_state?: string | null; in_bps?: number | null; out_bps?: number | null; utilization?: number | null
  latency_ms?: number | null; loss?: number | null
}
export interface DnsResolver extends ServiceState {
  id: string; name: string; address: string; lookup: string; latency_ms?: number | null; rcode?: string | null; answers?: number | null
}
export interface InternetSite extends ServiceState {
  id: string; name: string; host: string; port: number; latency_ms?: number | null; loss?: number | null
}
export interface LanCacheState {
  status: ServiceStatus; hit_ratio: number | null; served_bytes: number; bps: number
  disk: { used: number; total: number; ratio: number } | null; error: string; demo: boolean
}
export interface Services {
  uplinks: IspUplink[]; resolvers: DnsResolver[]; sites: InternetSite[]; lan_cache: LanCacheState | null
  interval: number; last_poll: number | null; via_agent: boolean; probe_ports: number[]; devices: string[]
}

/** One speed test the player ran from the seat's help page (issue #99). */
export interface SeatSpeedTest { down_mbps: number | null; up_mbps: number | null; ping_ms: number | null; jitter_ms?: number | null; at: number }

/** GET /api/plan/find: a player by nick, IP or MAC, and the hall their seat is in (issue #186). */
export interface PlayerHit { seat: string; nick: string; matched: string; hall: string }

/** A crew note on a seat (issue #180). */
export interface SeatNote { text: string; by: string | null; at: number }

/** One seat block for the Seats view's block panel (issue #174). */
export interface BlockDetails {
  name: string
  hall: string
  seats: number
  online: number
  offline: number
  unknown: number
  checked_in: number | null
  bps: number
  problems: { seat: string; state: SeatState; problems: number }[]
  switches: { name: string; seats: number; online: number; status: string }[]
  no_port: number
}

/** One switch for the Seats view's switch panel (issue #176). */
export interface SwitchDetails {
  name: string
  status: string
  since: number | null
  model: string | null
  online: number
  seats: { seat: string; port: string; state: SeatState; problems: number }[]
  /** Its planned links (topology) and what LLDP or CDP sees on ports no link explains (issue #540). */
  links?: { id: string; port: string; to: string; to_port: string; type: LinkType | ''; speed: number | null; issue: '' | 'down' | 'slow'; lldp: LinkLldp | null }[]
  neighbours?: { port: string; remote: string; remote_port: string; protocol: string }[]
}

/** GET /api/notice (issue #246): the lead's message to the whole crew. */
export interface CrewNotice {
  text: string
  level: 'info' | 'warn'
  /** Unix time it ends, or null: until a lead takes it down. */
  until: number | null
  by: string | null
  at: number
}

/** A page for the "Go to" palette, from GET /api/pages (issues #242, #250): the server picks the
 *  pages this account may open with the features and set-up this event has, so the floor plan,
 *  Settings and the React pages all offer the same list. */
export interface PageLink {
  href: string
  /** Key under goto.pages in the i18n files; ``label`` is the English fallback. */
  id: string
  label: string
}

/** A seat or switch for "Go to", from GET /api/pages/find (issue #252). */
export interface Place {
  /** player: a nick, IP or MAC and its seat, only for seats.view (issue #292); endpoint: where an
   *  IP or MAC was seen, from the history (also seats.view). */
  kind: 'seat' | 'switch' | 'player' | 'endpoint'
  name: string
  href: string
}

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
  /** Hall ids it answers for; empty: every hall. */
  halls?: string[]
  /** What it sent in the last ten minutes besides answers: syslog lines kept, flow summaries. */
  relays?: { syslog?: { at: number; count: number }; flows?: { at: number; count: number } }
  /** The agent's own numbers, sent every half minute (null: none lately, or an older agent). */
  report?: AgentReport | null
  /** Plugins that are on here but this agent leaves off (another agent runs them). */
  plugins_off?: string[]
  /** How it reaches this Floorbit right now: protocol 2's WebSocket link or the HTTPS long poll
   *  (null: not connected, or connected to another instance). */
  transport?: 'websocket' | 'poll' | null
  /** When its key was made, and until when the key before still works (after "New key"). */
  renewed_at?: number
  old_works_until?: number | null
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

/** Agents that serve the same halls, and how their failover stands (floorbit/agent_ha.py). */
export interface AgentGroup {
  id: string
  halls: string[]
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

/** GET /api/speedtests/summary (issue #434): each seat's latest test, for the hall and per switch. */
export interface SpeedFigures { tests: number; down_mbps: number | null; up_mbps: number | null; ping_ms: number | null }
export interface SpeedSeat { seat: string; down_mbps: number | null; up_mbps: number | null; ping_ms: number | null; at: number }
export interface SpeedSwitch extends SpeedFigures { id: string; name: string; seats: SpeedSeat[]; slow: boolean }
export interface SpeedtestSummary { hours: number; hall: SpeedFigures; switches: SpeedSwitch[]; unknown: SpeedSeat[] }

/** Game servers (issue #472): their last answer, and whether RCON is set up. Never the password. */
export interface GameServerInfo {
  name: string; map: string; game: string; version: string
  players: number; max_players: number; bots: number; ping_ms: number | null
}
export interface GameServer {
  id: string; name: string; game: string; host: string; port: number; query: 'a2s' | 'minecraft' | 'tcp'
  rcon_port: number | null; rcon: boolean
  /** The inventory server or VM it runs on, or ''. */
  runs_on?: string
  status: 'up' | 'down' | 'unknown'; info: GameServerInfo | null; error: string
  checked_at: number | null; since: number | null
  /** [when, players] oldest first; players is null while it was down. */
  history: [number, number | null][]
}
export interface GameServerList {
  servers: GameServer[]; interval: number; last_poll: number | null; via_agent: boolean
  counts: { up: number; down: number; unknown: number }; players: number
}
export interface RconAnswer { server: string; command: string; answer: string }

/** Links between switches and the topology (issue #468). */
export type LinkType = 'cat5e' | 'cat6' | 'cat6a' | 'fiber-sm' | 'fiber-mm' | 'dac'
export interface SwitchLink {
  id: string; a: string; a_port: string; b: string; b_port: string; type: LinkType | ''; speed: number | null; note: string
  media: 'copper' | 'fiber' | 'dac' | ''
  state: 'up' | 'down' | 'unknown'; speed_bps: number | null; issue: '' | 'down' | 'slow'
  /** What LLDP or CDP sees on its ports (issue #540); null when the source doesn't tell. */
  lldp?: LinkLldp | null
}
export interface LinkLldp { state: 'seen' | 'other' | 'unseen'; at?: 'a' | 'b'; remote?: string; remote_port?: string }
export interface TopologyNode { id: string; name: string; role: string; hall: string; unread: boolean; status: 'online' | 'offline' | 'unknown' }
export interface LinkSuggestion { a: string; a_port: string; b: string; b_port: string; protocol: string; speed: number | null }
/** An internet line from the services view (issue #471), drawn above the box it comes in at. */
export interface TopologyUplink {
  id: string; name: string; device: string; port: string; capacity_mbps: number | null
  status: 'up' | 'warn' | 'down' | 'unknown'; utilization: number | null
}
/** A switch's port for the link form's picker (GET /api/links/ports). */
export interface SwitchPort { name: string; state: string; speed_bps: number | null; used_by: string }
export interface Topology {
  nodes: TopologyNode[]; links: SwitchLink[]; uplinks: TopologyUplink[]; suggestions: LinkSuggestion[]
  counts: { links: number; down: number; slow: number; miswired?: number }; types: LinkType[]; speeds: number[]
  /** Where the crew dragged the boxes, by switch name in lower case; missing or empty: the automatic layout. */
  layout?: Record<string, { x: number; y: number }>
}
/** One kept switch config (floorbit/config_backup.py, issue #96). */
export interface ConfigCopy {
  id: string
  at: number
  by: string
  sha: string
  lines: number
}

export interface ConfigRow {
  switch: string
  copies: number
  last: ConfigCopy | null
  checked: { at: number; by: string } | null
  baseline: ConfigCopy | null
  changed: boolean
}

/** GET /api/configs. */
export interface ConfigOverview {
  available: boolean
  plugin: string | null
  needs_login: boolean
  switches: ConfigRow[]
  keep: number
  max_switches: number
  /** The backup every night with the stored switch logins. */
  nightly: ConfigNightly
}
export interface ConfigNightly {
  /** Server hour (0-23), or null when it's off. */
  hour: number | null
  covered: number
  switches: number
  last: { at: number; switches: number; ok: number; changed: string[]; failed: { switch: string; error: string }[] } | null
}

/** GET /api/configs/<switch>. */
export interface ConfigHistory {
  switch: string
  copies: ConfigCopy[]
  baseline: string | null
  checked: { at: number; by: string } | null
}

/** GET /api/configs/<switch>/diff. */
export interface ConfigDiff {
  from: ConfigCopy
  to: ConfigCopy
  lines: string[]
  added: number
  removed: number
}

export interface ConfigBackupResult {
  switch: string
  ok: boolean
  error: string | null
  copy?: ConfigCopy
  changed?: boolean
}

/** GET /api/auth/login-options: what the sign-in page offers (auth/__init__.py). */
export interface LoginOptions {
  enabled: boolean
  password_login: boolean
  providers: { id: string; label: string; url: string }[]
  no_users: boolean
  checkin_url: string | null
  /** The short address to type on a PC (CHECKIN_ADDRESS), e.g. checkin.lan. */
  checkin_address?: string | null
  next: string
  /** Why the last try failed (a wrong password, a provider that said no), shown once. */
  error: string | null
  username: string
}

/** GET /api/checkin/info: the attendee check-in page's state (integrations/__init__.py). */
export interface CheckinInfo {
  open: boolean
  /** When the event starts, if the schedule says and it's still ahead. */
  opens_at: number | null
  ip: string | null
  checkin: { seat: string; username: string; wired?: 'pending' | 'verified' | 'not_wired' | 'unverified' | null } | null
  /** False when the browser says it's a phone or tablet (a hint only). */
  on_pc?: boolean
  /** The seat this PC is known to be at (its port is patched or learned), as a hint. */
  suggested_seat?: string | null
  /** True: the seat number alone is refused, the PIN from the seat card is needed. */
  pin_required?: boolean
  /** The short address to type on a PC (CHECKIN_ADDRESS), e.g. checkin.lan. */
  address?: string | null
  /** True: not through the local agent's front door, so the seat's port can't be learned from here. */
  outside?: boolean
  /** Outside on a PC: the agent's front door that knows this PC (url), and whether Floorbit is sure
   *  this browser is in the hall, so the page goes there by itself (sure). */
  hall?: { url: string; sure: boolean } | null
}

export type WiredState = 'pending' | 'verified' | 'not_wired' | 'unverified'

/** One row of GET /api/checkins/overview (integrations/checkin.py overview). */
export interface CrewCheckin {
  seat: string
  username: string | null
  ip: string | null
  mac: string | null
  device: 'pc' | 'mobile' | 'unknown'
  wired: WiredState
  /** The switch port the background lookup found for this check-in. */
  port: { switch: string; port: string } | null
  /** The port the seat is learned on (seat_ports.json), from a PIN check-in. */
  learned: { switch: string; port: string; learned_at: number; username?: string } | null
  pin: boolean
  /** The rough area the found port goes to, when the crew gave one. */
  area?: PortAreaHint | null
  checked_in_at: number | null
  verified_at: number | null
  /** What asking the switches said (docs/segments.md), when it says something for the crew. */
  lookup?: CheckinLookup | null
}

/** One check-in's switch lookup: a to-do when it couldn't ask. */
export interface CheckinLookup {
  state: 'found' | 'not_found' | 'todo' | 'closed' | 'error'
  todo?: 'no_segment' | 'segment_off' | 'no_core'
  vlan?: number
}

/** When check-ins may ask the switches (GET /api/checkins/lookup-window). */
export interface LookupWindow {
  open: boolean
  until: number | null
  why: 'doors' | 'by_hand' | 'activity' | null
  doors: number | null
  hours: number
  segments_on: number
}

export interface CheckinConflict {
  kind: 'shared' | 'plan' | 'taken' | 'area'
  seat: string
  /** The other seats on that port (shared), or the seat the patch plan gives it to (plan). */
  other: string[]
  switch: string
  port: string
}

/** GET /api/checkins/overview: the crew's Check-in page. */
export interface CheckinOverview {
  counts: Record<WiredState, number> & {
    checked_in: number; conflicts: number; learned: number; unused_pins: number; pins: number
  }
  rows: CrewCheckin[]
  conflicts: CheckinConflict[]
  portal: { fetches: { at: number; agent: string | null; done: number }[]; public_url: string | null }
  verifier: { last_error: string | null }
  lookups?: LookupWindow
}

/** One row of the IP and MAC history (floorbit/endpoints.py): a machine seen on a port. */
export interface EndpointRow {
  mac: string
  ip: string | null
  device: string
  port: string | null
  seat: string | null
  vlan: number | null
  first_seen: number
  last_seen: number
}

export interface EndpointAnswer {
  rows: EndpointRow[]
  status: { store: 'database'; written: number; open: number; keep_days: number; error: string | null }
}
