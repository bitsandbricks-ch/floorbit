import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { qk } from './keys'
import type {
  AccountSummary,
  InventoryList,
  LogLine,
  OidcList,
  Me,
  Permission,
  PluginInfo,
  RolesList,
  SeatMapList,
  Team,
  Tile,
  Widget,
  WidgetTile,
} from './types'

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

/** Does the signed-in account's role have this permission? Everyone may when sign-in is off.
 *  Only hides buttons: the server checks every request anyway (auth/roles.py). */
export function useCan(permission: Permission) {
  const me = useMe().data
  if (!me) return false
  if (!me.enabled) return true
  return !!me.user?.permissions?.includes(permission)
}

export function useInventory(hidden: boolean) {
  return useQuery({
    queryKey: qk.inventory(hidden),
    queryFn: () => get<InventoryList>(`/api/inventory${hidden ? '?hidden=1' : ''}`),
  })
}

export function useSeatMap() {
  return useQuery({ queryKey: qk.seatMap, queryFn: () => get<SeatMapList>('/api/seat-map') })
}

export function useRoles() {
  return useQuery({ queryKey: qk.roles, queryFn: () => get<RolesList>('/api/roles') })
}

export function useOidcProviders() {
  return useQuery({ queryKey: qk.oidc, queryFn: () => get<OidcList>('/api/settings/oidc') })
}

export function useTeams() {
  return useQuery({ queryKey: qk.teams, queryFn: () => get<{ teams: Team[] }>('/api/teams') })
}

export function useAccounts() {
  return useQuery({ queryKey: qk.users, queryFn: () => get<{ users: AccountSummary[] }>('/api/users') })
}
