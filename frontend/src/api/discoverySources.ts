import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './client'
import { qk } from './keys'

/** Who decides a discovery area: the admin picked it, the default order did, or it's the only one. */
export type DecidingWhy = 'admin' | 'default' | 'only' | 'none'

/** One row of "What Floorbit reads from a <kind of device>" (issue #965). */
export interface ReadsRow {
  area: string
  name: string
  builtin: boolean
  /** Who reads it on such devices, in the default order; 'monitoring' is the monitoring source. */
  sources: { id: string; name: string }[]
  deciding: string | null
  why: DecidingWhy
  /** Minutes between runs of the deciding source's action, 0 when off. */
  minutes: number | null
  action: string | null
  /** fields, interfaces, discovered.<key> or auto.<area>.* */
  goes_to: string
  last: { at: string; devices: number; changed: number; error?: string } | null
  conflicts: number
}

export interface Reads { role: string; devices: number; monitoring: string | null; rows: ReadsRow[] }

/** Where a source that doesn't decide read another value than the one that does. */
export interface SourceConflict {
  kind: 'conflict'
  field: string
  why: DecidingWhy
  deciding: { source: string; name: string; value: string | number }
  other: { source: string; name: string; value: string | number }
  since?: string | null
}

const readsKey = (role: string) => ['inventory', 'discovery', 'types', role] as const

export function useReads(role: string) {
  return useQuery({ queryKey: readsKey(role), queryFn: () => get<Reads>(`/api/inventory/discovery/types/${encodeURIComponent(role)}`) })
}

/** An admin picks the deciding source of an area for a kind of device; null goes back to the default. */
export function usePickDeciding() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (p: { role: string; area: string; source: string | null }) => put<Reads>('/api/inventory/discovery/deciding', p),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.inventoryAll }),
  })
}

/** The device's field takes one source's reading, like a hand edit. */
export function useTakeConflict(deviceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (p: { field: string; source: string }) => post(`/api/inventory/${encodeURIComponent(deviceId)}/conflicts/take`, p),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.inventoryAll }),
  })
}

export const readsPath = (role: string) => `/inventory/reads/${encodeURIComponent(role)}`
