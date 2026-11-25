import { useQueries, useQuery } from '@tanstack/react-query'
import { get } from './client'
import { qk } from './keys'
import { getWidget } from './widgetBatch'
import type { CustomSection } from '@/nav/sections'
import type {
  PageLink,
  Place,
  CrewNotice,
  AccountSummary,
  IncidentBoard,
  IncidentPeople,
  InventoryList,
  LogLine,
  OidcList,
  Me,
  Permission,
  PluginList,
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
  FlowsData,
} from './types'

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: () => get<Me>('/api/auth/me'), staleTime: 60_000 })
}

/** Is this feature switched on (Settings > Plugins > Built in)? On until the server says otherwise, so a slow
 *  answer never hides a link. Only hides links: a feature that is off answers 404 anyway. */
export function useFeature(feature: string) {
  return !useFeaturesOff().includes(feature)
}

/** The features that are switched off; empty until the server answers. */
export function useFeaturesOff(): string[] {
  const off = useQuery({ queryKey: qk.features, queryFn: () => get<{ off: string[] }>('/api/features'), staleTime: 60_000, retry: false })
  return off.data?.off ?? []
}

/** The pages this account may open, for "Go to" (issue #250); empty until the server answers. */
export function usePageList(): PageLink[] {
  return usePagesQuery().data?.pages ?? []
}

/** Has the page list answered (or failed)? Until then nobody knows what this account may open. */
export function usePageListSettled(): { settled: boolean; failed: boolean } {
  const q = usePagesQuery()
  return { settled: !q.isPending, failed: q.isError }
}

/** The sidebar sections admins made, as this account sees them; null until the server answers. */
export function useCustomSections(): CustomSection[] | null {
  return usePagesQuery().data?.custom ?? null
}

function usePagesQuery() {
  return useQuery({
    queryKey: qk.pages, queryFn: () => get<{ pages: PageLink[]; custom?: CustomSection[] }>('/api/pages'), staleTime: 60_000, retry: false,
  })
}

/** Seats and switches whose number or name matches, for "Go to" (issue #252); needs two characters. */
export function usePlaces(query: string): Place[] {
  const q = query.trim()
  const places = useQuery({
    queryKey: qk.places(q), queryFn: () => get<{ places: Place[] }>(`/api/pages/find?q=${encodeURIComponent(q)}`),
    enabled: q.length >= 2, staleTime: 30_000, retry: false,
  })
  return q.length >= 2 ? places.data?.places ?? [] : []
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

/** Several widgets at once (a pane with more than one source), each on its own refresh. */
export function useWidgets(tiles: WidgetTile[]) {
  return useQueries({
    queries: tiles.map((tile) => ({
      queryKey: qk.widget(tile.url),
      queryFn: () => getWidget<Widget>(tile.url),
      refetchInterval: Math.max(10, tile.refresh) * 1000,
      refetchIntervalInBackground: false,
    })),
  })
}

export function usePlugins() {
  return useQuery({ queryKey: qk.plugins, queryFn: () => get<PluginList>('/api/settings/plugins') })
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
  return useQuery({ queryKey: qk.seatMap, queryFn: () => get<SeatMapList>('/api/seat-map?read=1') })
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
  return useQuery({ queryKey: qk.helpdeskQr, queryFn: () => get<{ seats: QrSeat[]; checkin?: { address: string | null; url: string | null } | null }>('/api/helpdesk/qr') })
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

/** Kept current by useLiveRefresh (api/liveRefresh.ts), once per page: an interval here would run
 *  once per component that shows the list, each on its own clock. */
export function useProblems(enabled = true) {
  return useQuery({ queryKey: qk.problems, queryFn: () => get<ProblemList>('/api/problems'), enabled })
}

export function useStats(screen = false) {
  return useQuery({
    queryKey: qk.stats(screen),
    queryFn: () => get<StatsData>(screen ? '/api/stats?screen=1' : '/api/stats'),
    refetchInterval: 30_000,
  })
}

export function useFlows() {
  return useQuery({ queryKey: qk.flows, queryFn: () => get<FlowsData>('/api/flows'), refetchInterval: 30_000 })
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

/** The notice that is up. A new or cleared one comes with a live event (api/liveRefresh.ts, on the
 *  page's one shared stream); the reads here are a safety net, and one just after it runs out. */
export function useNotice() {
  const me = useMe().data
  return useQuery({
    queryKey: qk.notice,
    queryFn: () => get<{ notice: CrewNotice | null }>('/api/notice'),
    refetchInterval: (query) => noticeRecheck(query.state.data?.notice ?? null),
    // Signed-out pages (and the sign-in screen) have nothing to show.
    enabled: !!me && (!me.enabled || !!me.user),
  })
}

const NOTICE_RECHECK_MS = 5 * 60_000

/** When to read the notice again: in five minutes, or a second after it runs out if that is sooner. */
export function noticeRecheck(notice: CrewNotice | null, now = Date.now()): number {
  if (!notice?.until) return NOTICE_RECHECK_MS
  return Math.min(NOTICE_RECHECK_MS, Math.max(1000, notice.until * 1000 - now + 1000))
}
