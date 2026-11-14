import { INVENTORY_FIELDS, type Device, type InventoryField } from '@/api/types'

export type Draft = Record<InventoryField, string>

const EMPTY: Draft = { name: '', role: 'switch', model: '', serial: '', mgmt_ip: '', hall: '', status: '', notes: '' }

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
  return [device.name, device.model, device.serial, device.mgmt_ip, device.hall, device.status, device.notes]
    .some((v) => (v || '').toLowerCase().includes(q))
}

