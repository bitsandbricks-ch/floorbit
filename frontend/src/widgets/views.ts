import { type ComponentType, type LazyExoticComponent, lazy } from 'react'

/** Rich widgets ("views"): a chart, a map, a table with filters, more than the data widgets
 *  (WidgetBody.tsx) can draw. A Dashboard pane shows one (pane kind ``view``), and a widget opened
 *  to its expanded size is the same component with ``expanded``. One line per view below; the
 *  component lives with its feature (``pages/<area>/...View.tsx``) and has no page or route of its own. */
export interface ViewProps {
  /** Shown big (a pane of its own, or a widget opened up): room for filters, search and actions. */
  expanded: boolean
}

export interface ViewDef {
  id: string
  /** Groups views in the Widgets gallery and the pane settings: network, services, traffic, ... */
  area: string
  /** i18n key of its name. */
  label: string
  /** The permission it needs (auth/roles.py); the server checks its data calls either way. */
  permission?: string
  /** The feature it belongs to (Settings > Features): off, the gallery leaves it out. */
  feature?: string
  load: () => Promise<{ default: ComponentType<ViewProps> }>
}

export const VIEWS: ViewDef[] = [
  { id: 'health', area: 'services', label: 'health.title', feature: 'health', load: () => import('@/pages/health/HealthView') },
  { id: 'services', area: 'services', label: 'services.title', load: () => import('@/pages/services/ServicesView') },
  { id: 'lancache', area: 'services', label: 'lancache.title', load: () => import('@/pages/lancache/LancacheView') },
  { id: 'stats', area: 'network', label: 'stats.title', load: () => import('@/pages/stats/StatsView') },
  { id: 'network-status', area: 'network', label: 'status.title', feature: 'status_page', permission: 'incidents.work',
    load: () => import('@/pages/status/NetworkStatusView') },
  { id: 'wifi', area: 'network', label: 'wifi.title', feature: 'wifi', load: () => import('@/pages/wifi/WifiView') },
  { id: 'endpoints', area: 'network', label: 'endpoints.title', permission: 'seats.view', load: () => import('@/pages/endpoints/EndpointsView') },
  { id: 'agents', area: 'network', label: 'agents.title', permission: 'settings.manage', load: () => import('@/pages/agents/AgentsView') },
  { id: 'traffic', area: 'traffic', label: 'traffic.title', feature: 'traffic', load: () => import('@/pages/traffic/TrafficView') },
  { id: 'dns', area: 'traffic', label: 'dns.title', feature: 'dns', load: () => import('@/pages/dns/DnsView') },
  { id: 'games', area: 'traffic', label: 'games.title', feature: 'games', load: () => import('@/pages/games/GamesView') },
  { id: 'speedtests', area: 'traffic', label: 'speedtests.title', feature: 'helpdesk', permission: 'incidents.work',
    load: () => import('@/pages/speedtests/SpeedtestsView') },
  { id: 'event-numbers', area: 'network', label: 'publicWall.title', feature: 'stats_wall', load: () => import('@/pages/wall/EventNumbersView') },
  { id: 'power-load', area: 'power', label: 'power.loadTitle', feature: 'power', load: () => import('@/pages/power/PowerLoadView') },
]

/** Each view's component, loaded on first use. */
export const VIEW_COMPONENTS: Record<string, LazyExoticComponent<ComponentType<ViewProps>>> =
  Object.fromEntries(VIEWS.map((v) => [v.id, lazy(v.load)]))
