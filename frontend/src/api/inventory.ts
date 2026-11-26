export const INVENTORY_FIELDS = ['name', 'role', 'model', 'serial', 'mgmt_ip', 'hall', 'status', 'notes',
  'platform', 'os', 'cpu', 'cores', 'memory_mb', 'disk_gb', 'host', 'location'] as const
export type InventoryField = (typeof INVENTORY_FIELDS)[number]
export const SPEC_FIELDS = ['platform', 'os', 'cpu', 'cores', 'memory_mb', 'disk_gb', 'host'] as const

/** A device's link towards the core, in the inventory list (issue #981). */
export interface DeviceUplink {
  port: string; peer: string; peer_port: string; speed_bps: number | null; planned_gbps: number | null
  state: 'up' | 'down' | 'unknown'; issue: '' | 'down' | 'slow'
  /** How full the busiest direction is, 0 to 1 (Network › Switches, #902); null when not read. */
  load?: number | null
}

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
  /** In the list only (issue #981): the link towards the core, seconds down in each of the last 24
   *  hours (oldest first; none when the monitor never reported it), and telemetry.agent ('' Auto). */
  uplink?: DeviceUplink | null
  last_day?: number[] | null
  agent?: string
  /** In the list only (issue #902): seats on its ports, and its PoE budget and draw in watts. */
  seats?: number
  poe?: { budget_w: number; used_w: number } | null
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
  /** False: the plugin doesn't work on inventory devices, so switching it per device does nothing. */
  per_device?: boolean
  /** The device roles it is about; null: any (#878). */
  roles?: string[] | null
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
  /** VLANs and prefixes: the devices discovery read them on (issue #1347). */
  seen_on?: { id: string; name: string }[]
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

export interface DeviceDetail extends Omit<Device, 'drift'> {
  /** The list here; the inventory list has only the count. */
  drift?: import('./inventoryDrift').DriftRow[]
  /** Where two discovery sources read different values (issue #965). */
  conflicts?: import('./discoverySources').SourceConflict[]
  interfaces: DeviceInterface[]
  own_credentials: CredentialInfo[]
  blocks: LoginBlock[]
  /** What discovery read from the device (issue #919): its VLANs, the networks on its interfaces,
   *  the VLAN interfaces with an address, and a firewall's routes; ``at`` is when. */
  discovered?: {
    vlans: { id: number; name: string }[]
    networks: string[]
    svis?: { vlan: number; network: string; if_index?: number | null }[]
    routes: { network: string; next_hop?: string | null; interface?: string | null; proto?: string | null }[]
    at: string | null
  }
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
