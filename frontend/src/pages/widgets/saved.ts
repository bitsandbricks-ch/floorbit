import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import type { Pane } from '../dashboards/model'

export type TilePane = Extract<Pane, { kind: 'tile' }>

/** A saved widget (floorbit/saved_widgets.py, #1009): a tile pane under a name, for any dashboard.
 *  ``used_on``: the dashboards that show it, which keep it from being removed. */
export interface SavedWidget { id: string; name: string; pane: TilePane; updated_at?: number; by?: string | null; used_on: string[] }

export function useSavedWidgets(enabled = true) {
  return useQuery({ queryKey: qk.savedWidgets, queryFn: () => get<{ widgets: SavedWidget[] }>('/api/widgets'), enabled })
}

/** Saves a new widget (no ``id``) or replaces one; dashboards that show it follow. */
export function useSaveWidget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name, pane }: { id?: string; name: string; pane: TilePane }) =>
      id ? put<SavedWidget>(`/api/widgets/${encodeURIComponent(id)}`, { name, pane }) : post<SavedWidget>('/api/widgets', { name, pane }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.savedWidgets })
      void qc.invalidateQueries({ queryKey: qk.boards })
    },
  })
}

export function useDeleteWidget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del<{ ok: true }>(`/api/widgets/${encodeURIComponent(id)}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.savedWidgets }),
  })
}

/** The tile pane a widget pane draws: the saved one, under the pane's own title if it has one. */
export const followed = (saved: { name: string; pane: TilePane }, head: { title?: string; hide_title?: boolean }): TilePane =>
  ({ ...saved.pane, title: head.title || saved.name, ...(head.hide_title ? { hide_title: true } : {}) })
