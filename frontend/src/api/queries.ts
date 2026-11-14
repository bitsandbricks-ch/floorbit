import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { qk } from './keys'
import type {
  AccountSummary,
  IncidentBoard,
  IncidentPeople,
  InventoryList,
  LogLine,
  OidcList,
  Me,
  Permission,
  PluginInfo,
  QrSeat,
  HealthWall,
  SecurityList,
  PowerOverview,
  ProblemList,
  RolesList,
  SeatMapList,
  SetupState,
  Team,
  Tile,
  Widget,
  WidgetTile,
  StatsData,
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

// The board refreshes on its own; live events refresh it sooner (see pages/Incidents.tsx).
export function useIncidents() {
  return useQuery({ queryKey: qk.incidents, queryFn: () => get<IncidentBoard>('/api/incidents'), refetchInterval: 30_000 })
}

export function useIncidentPeople() {
  return useQuery({ queryKey: qk.incidentPeople, queryFn: () => get<IncidentPeople>('/api/incidents/people') })
}

export function useHelpdeskQr() {
  return useQuery({ queryKey: qk.helpdeskQr, queryFn: () => get<{ seats: QrSeat[] }>('/api/helpdesk/qr') })
}

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: () => get<HealthWall>('/api/health'), refetchInterval: 30_000 })
}

export function useSecurity() {
  return useQuery({ queryKey: qk.security, queryFn: () => get<SecurityList>('/api/security'), refetchInterval: 30_000 })
}

export function usePower() {
  return useQuery({ queryKey: qk.power, queryFn: () => get<PowerOverview>('/api/power'), refetchInterval: 30_000 })
}

export function useProblems() {
  return useQuery({ queryKey: qk.problems, queryFn: () => get<ProblemList>('/api/problems'), refetchInterval: 30_000 })
}

export function useStats(screen = false) {
  return useQuery({
    queryKey: qk.stats(screen),
    queryFn: () => get<StatsData>(screen ? '/api/stats?screen=1' : '/api/stats'),
    refetchInterval: 30_000,
  })
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

export function useSetup() {
  return useQuery({ queryKey: qk.setup, queryFn: () => get<SetupState>('/api/setup') })
}
