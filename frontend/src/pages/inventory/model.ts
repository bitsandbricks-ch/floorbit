import { INVENTORY_FIELDS, type Device, type InventoryField, type InventoryGroup } from '@/api/types'

export type Draft = Record<InventoryField, string>

const EMPTY: Draft = {
  name: '', role: 'switch', model: '', serial: '', mgmt_ip: '', hall: '', status: '', notes: '',
  platform: '', os: '', cpu: '', cores: '', memory_mb: '', disk_gb: '', host: '',
}

/** Roles whose specs (platform, OS, CPU, memory, ...) the form shows without asking. */
export const SPEC_ROLES = ['server', 'vm', 'firewall', 'router']

export function draftOf(device: Device | null): Draft {
  if (!device) return { ...EMPTY }
  return Object.fromEntries(INVENTORY_FIELDS.map((f) => [f, device[f] ?? ''])) as Draft
}

/** What a plugin last sent for a field, and which plugin. */
export function fedValue(device: Device, field: InventoryField): { source: string; value: string } | null {
  for (const source of device.sources) {
    const value = device.fed[source]?.[field]
    if (value !== undefined) return { source, value }
  }
  return null
}

export function matches(device: Device, query: string, role: string | null) {
  if (role && device.role !== role) return false
  const q = query.trim().toLowerCase()
  if (!q) return true
  return [device.name, device.model, device.serial, device.mgmt_ip, device.hall, device.status, device.notes, device.platform, device.os, device.host]
    .some((v) => (v || '').toLowerCase().includes(q))
}

/** The icon, colour and tags a device shows: its own, else the nearest group's (tags: all of them).
 *  Tags' own icons and colours are left to the device page, which has the full lookup. */
export function effectiveLook(device: Device, groups: InventoryGroup[]) {
  const byId = new Map(groups.map((g) => [g.id, g]))
  let icon = device.icon ?? ''
  let color = device.color ?? ''
  const tags = new Set(device.tags ?? [])
  const seen = new Set<string>()
  let id = device.group_id ?? null
  while (id && byId.has(id) && !seen.has(id)) {
    seen.add(id)
    const g = byId.get(id)!
    icon = icon || g.icon
    color = color || g.color
    g.tags.forEach((x) => tags.add(x))
    id = g.parent_id
  }
  return { icon, color, tags }
}

/** A role's own icon, when nothing chose another one. */
const ROLE_ICONS = ['switch', 'router', 'firewall', 'server', 'vm', 'access-point', 'pdu']
export function roleIcon(role: string) {
  return ROLE_ICONS.includes(role) ? role : 'other'
}

export function speedLabel(mbps: number | null | undefined) {
  if (!mbps) return ''
  return mbps >= 1000 ? `${+(mbps / 1000).toFixed(1)}G` : `${mbps}M`
}

export function credentialBody(ownerType: string, ownerId: string, d: { kind: string; username: string; secret: string; priv_secret: string; auth_protocol: string; priv_protocol: string }) {
  return {
    owner_type: ownerType, owner_id: ownerId, kind: d.kind, username: d.username,
    ...(d.secret ? { secret: d.secret } : {}),
    ...(d.kind === 'snmp_v3' ? { auth_protocol: d.auth_protocol, priv_protocol: d.priv_protocol, ...(d.priv_secret ? { priv_secret: d.priv_secret } : {}) } : {}),
  }
}
