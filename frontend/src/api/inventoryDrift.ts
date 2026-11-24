import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import { qk } from './keys'

/** Where the inventory and what the device reports disagree, from discovery (issue #918). */
export interface DriftRow {
  kind: 'field' | 'hostname' | 'address' | 'interface'
  /** The inventory field, or for an interface its name and maybe the field ("Gi1/0/1 speed"). */
  field: string
  configured: string | number | boolean | null
  actual: string | number | boolean | null
  /** When discovery first saw it (ISO time). */
  since?: string
}

/** Kinds the device's value can be taken for in one click; a hostname or an interface can't. */
export const TAKES: DriftRow['kind'][] = ['field', 'address']

export function useTakeDrift(deviceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (field: string) => post(`/api/inventory/${encodeURIComponent(deviceId)}/drift/take`, { field }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.inventoryAll }),
  })
}

export interface DriftDevice { id: string; name: string; drift: DriftRow[] }

/** Every device that differs, for the inventory's drift view. Under 'inventory', so a take refreshes it. */
export function useDriftAll(enabled: boolean) {
  return useQuery({
    queryKey: ['inventory', 'drift'] as const,
    queryFn: () => get<{ devices: DriftDevice[] }>('/api/inventory/drift'),
    enabled,
  })
}
