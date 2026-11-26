import { type ComponentType, type LazyExoticComponent, lazy } from 'react'

/** What a monitoring page's body gets. ``expanded`` is always true now that the bodies are pages
 *  only (the dashboard ``view`` pane is gone, #1045); the bodies still read it for their layout. */
export interface ViewProps {
  expanded: boolean
}

/** The Monitoring pages drawn by ViewPage: the i18n key of each title and its body. */
const PAGES = {
  wifi: { label: 'wifi.title', load: () => import('@/pages/wifi/WifiView') },
  dns: { label: 'dns.title', load: () => import('@/pages/dns/DnsView') },
  traffic: { label: 'traffic.title', load: () => import('@/pages/traffic/TrafficOverview') },
  games: { label: 'games.title', load: () => import('@/pages/games/GamesAndDownloads') },
  speedtests: { label: 'speedtests.title', load: () => import('@/pages/speedtests/SpeedtestsView') },
} satisfies Record<string, { label: string; load: () => Promise<{ default: ComponentType<ViewProps> }> }>

export type MonitoringPage = keyof typeof PAGES

export const PAGE_LABEL: Record<MonitoringPage, string> =
  Object.fromEntries(Object.entries(PAGES).map(([id, p]) => [id, p.label])) as Record<MonitoringPage, string>

/** Each page's body, loaded on first use. */
export const PAGE_BODY: Record<MonitoringPage, LazyExoticComponent<ComponentType<ViewProps>>> =
  Object.fromEntries(Object.entries(PAGES).map(([id, p]) => [id, lazy(p.load)])) as Record<MonitoringPage, LazyExoticComponent<ComponentType<ViewProps>>>
