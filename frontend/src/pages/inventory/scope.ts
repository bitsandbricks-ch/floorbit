import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { CredentialInfo, DeviceDetail, InventoryGroup, InventoryOverview } from '@/api/types'

export function useInventoryGroups() {
  return useQuery({ queryKey: qk.inventoryGroups, queryFn: () => get<InventoryOverview>('/api/inventory/groups') })
}

export function useDeviceDetail(id: string | null) {
  return useQuery({
    queryKey: qk.inventoryDevice(id ?? ''),
    queryFn: () => get<DeviceDetail>(`/api/inventory/${encodeURIComponent(id ?? '')}`),
    enabled: !!id,
  })
}

export function useCredentials(enabled: boolean) {
  return useQuery({
    queryKey: qk.inventoryCredentials,
    queryFn: () => get<{ credentials: CredentialInfo[] }>('/api/inventory/credentials'),
    enabled,
  })
}

/** Groups as a tree, in name order: [{group, depth}], parents before their children. */
export function groupTree(groups: InventoryGroup[]): { group: InventoryGroup; depth: number }[] {
  const ids = new Set(groups.map((g) => g.id))
  const children = new Map<string | null, InventoryGroup[]>()
  for (const g of groups) {
    const parent = g.parent_id && ids.has(g.parent_id) ? g.parent_id : null
    children.set(parent, [...(children.get(parent) ?? []), g])
  }
  const out: { group: InventoryGroup; depth: number }[] = []
  const walk = (parent: string | null, depth: number, seen: Set<string>) => {
    for (const g of [...(children.get(parent) ?? [])].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))) {
      if (seen.has(g.id)) continue
      seen.add(g.id)
      out.push({ group: g, depth })
      walk(g.id, depth + 1, seen)
    }
  }
  walk(null, 0, new Set())
  return out
}

/** A group and everything below it, for filtering the device list. */
export function groupAndBelow(groups: InventoryGroup[], id: string): Set<string> {
  const out = new Set([id])
  let grew = true
  while (grew) {
    grew = false
    for (const g of groups) {
      if (g.parent_id && out.has(g.parent_id) && !out.has(g.id)) {
        out.add(g.id)
        grew = true
      }
    }
  }
  return out
}
