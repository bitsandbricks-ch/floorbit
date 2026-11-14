import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { qk } from './keys'
import type { InventoryList, LogLine, Me, PluginInfo, Role, Tile, Widget, WidgetTile } from './types'

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: () => get<Me>('/api/auth/me'), staleTime: 60_000 })
}

export function useDashboard() {
  return useQuery({ queryKey: qk.dashboard, queryFn: () => get<{ tiles: Tile[] }>('/api/dashboard') })
}

export function useWidget(tile: WidgetTile) {
  return useQuery({
    queryKey: qk.widget(tile.url),
    queryFn: () => get<Widget>(tile.url),
    // The server already refuses less than 10 s; this keeps a broken manifest from hammering it.
    refetchInterval: Math.max(10, tile.refresh) * 1000,
    refetchIntervalInBackground: false,
  })
}

export function usePlugins() {
  return useQuery({ queryKey: qk.plugins, queryFn: () => get<{ plugins: PluginInfo[] }>('/api/settings/plugins') })
}

export function usePluginLog(id: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.pluginLog(id),
    queryFn: () => get<{ lines: LogLine[] }>(`/api/settings/plugins/${encodeURIComponent(id)}/log`),
    enabled,
  })
}

/** Editors and admins may change things; everyone may when sign-in is off. */
export function useCanEdit(needed: Role = 'editor') {
  const me = useMe().data
  if (!me) return false
  if (!me.enabled) return true
  const order: Role[] = ['viewer', 'editor', 'admin']
  return !!me.user && order.indexOf(me.user.role) >= order.indexOf(needed)
}

export function useInventory(hidden: boolean) {
  return useQuery({
    queryKey: qk.inventory(hidden),
    queryFn: () => get<InventoryList>(`/api/inventory${hidden ? '?hidden=1' : ''}`),
  })
}
