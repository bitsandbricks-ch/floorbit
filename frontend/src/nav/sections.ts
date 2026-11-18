import {
  IconActivityHeartbeat,
  IconDeviceDesktopSearch, IconAlertTriangle, IconApps, IconArchive, IconArmchair, IconArrowsExchange, IconBolt, IconBook,
  IconBroadcast, IconCalendar, IconCalendarEvent, IconChartLine, IconChartPie, IconChecklist, IconClipboardCheck,
  IconBell, IconDeviceTv, IconExternalLink, IconEye, IconFlag, IconFolder, IconHeart, IconLink, IconMap,
  IconDeviceGamepad2, IconFileText, IconGauge, IconHeartbeat, IconHistory, IconKey, IconLayoutCards, IconLayoutDashboard, IconLayoutGrid, IconLayoutSidebar,
  IconHeadset, IconHierarchy2, IconLifebuoy, IconListSearch, IconLogin, IconNetwork, IconPlayerPlay, IconPlug, IconPlugConnected, IconPuzzle, IconReport,
  IconServer, IconServer2, IconServerBolt, IconSettings, IconShield, IconStar, IconTableOptions, IconTemplate, IconTerminal, IconTerminal2, IconToggleRight,
  IconTools, IconTournament, IconTrophy, IconUserCheck, IconUsers, IconUsersGroup, IconWalk, IconWall, IconWebhook, IconWifi, IconWorldWww,
  type Icon,
} from '@tabler/icons-react'

/** A page as the server lists it (GET /api/pages, floorbit/page_index.py): only those this account may open. */
export interface NavPage {
  href: string; id: string; label: string
  /** A plugin's page (id ``plugin:<plugin>:<page>``): the plugin's icon name, and its label as the plugin gives it. */
  icon?: string
}

export type SectionId = 'helpdesk' | 'network' | 'build' | 'event' | 'admin' | 'plugins' | 'more'

/** A plugin's own page (plugin.yaml ``pages:``), which goes into the Plugins section. */
export const isPluginPage = (id: string) => id.startsWith('plugin:')

/** The pages crews open all the time: always at the top of the sidebar, never folded away. */
export const PINNED = ['floorPlan', 'seats', 'dashboards', 'problems', 'incidents']

/** The rest, folded into sections. A page the server lists that isn't here lands in "more",
 *  so a new page shows up before anyone sorts it in. */
export const SECTIONS: { id: SectionId; icon: Icon; pages: string[] }[] = [
  { id: 'helpdesk', icon: IconHeadset, pages: ['jobs', 'handover', 'runbooks', 'checkins', 'speedtests', 'networkStatus'] },
  {
    id: 'network', icon: IconNetwork,
    pages: ['dashboard', 'health', 'topology', 'endpoints', 'firewalls', 'services', 'stats', 'traffic', 'dns', 'games', 'gameServers', 'logs', 'security', 'wifi', 'power', 'commands', 'terminal'],
  },
  { id: 'build', icon: IconTools, pages: ['inventory', 'seatMapping', 'cables', 'seatWalk', 'preflight', 'templates'] },
  { id: 'event', icon: IconCalendarEvent, pages: ['tournament', 'brackets', 'schedule', 'timeline', 'replay', 'report', 'events'] },
  { id: 'admin', icon: IconSettings, pages: ['settings', 'plugins', 'features', 'sidebarSections', 'apiTokens', 'agents', 'telemetry', 'webhooks', 'users', 'teams', 'signIn', 'audit'] },
]

const ICONS: Record<string, Icon> = {
  floorPlan: IconLayoutGrid, seats: IconArmchair, dashboards: IconLayoutDashboard, dashboard: IconLayoutCards, problems: IconAlertTriangle,
  incidents: IconLifebuoy, jobs: IconClipboardCheck, handover: IconArrowsExchange, runbooks: IconBook,
  checkins: IconUserCheck, speedtests: IconGauge, networkStatus: IconBroadcast, health: IconHeartbeat, stats: IconChartLine, traffic: IconChartPie,
  dns: IconWorldWww, games: IconDeviceGamepad2, gameServers: IconServer2, topology: IconHierarchy2, firewalls: IconWall, services: IconServerBolt, logs: IconFileText, security: IconShield, wifi: IconWifi, power: IconBolt,
  commands: IconTerminal2, terminal: IconTerminal, inventory: IconServer, seatMapping: IconTableOptions, cables: IconPlug, seatWalk: IconWalk,
  preflight: IconChecklist, templates: IconTemplate,
  tournament: IconTrophy, brackets: IconTournament, schedule: IconCalendar, timeline: IconHistory, replay: IconPlayerPlay,
  report: IconReport, events: IconArchive, settings: IconSettings, plugins: IconPuzzle, features: IconToggleRight, sidebarSections: IconLayoutSidebar,
  apiTokens: IconKey, agents: IconPlugConnected, telemetry: IconActivityHeartbeat, endpoints: IconDeviceDesktopSearch, webhooks: IconWebhook, users: IconUsers, teams: IconUsersGroup, signIn: IconLogin, audit: IconListSearch,
}

export function pageIcon(id: string, icon?: string): Icon {
  if (isPluginPage(id)) return (icon && Object.hasOwn(CUSTOM_ICONS, icon) ? CUSTOM_ICONS[icon] : undefined) ?? IconPuzzle
  return ICONS[id] ?? IconApps
}

export function sectionIcon(id: SectionId): Icon {
  if (id === 'plugins') return IconPuzzle
  return SECTIONS.find((s) => s.id === id)?.icon ?? IconApps
}

/** A row in a section an admin made (floorbit/nav_sections.py): only the links this account may open. */
export interface CustomLink {
  kind: 'dashboard' | 'page' | 'url'
  href: string
  label: string
  /** A page link: the page's id, for its icon and (without ``own``) its name in the reader's language. */
  page?: string
  own?: boolean
  /** An address on another site: opens in a new tab. */
  external?: boolean
}
export interface CustomSection { id: string; name: string; icon: string; links: CustomLink[] }

/** The icons an admin can give a section; the same names as ICONS in floorbit/nav_sections.py. */
export const CUSTOM_ICONS: Record<string, Icon> = {
  dashboard: IconLayoutDashboard, star: IconStar, bolt: IconBolt, network: IconNetwork, server: IconServer,
  chart: IconChartLine, heart: IconHeart, users: IconUsers, trophy: IconTrophy, calendar: IconCalendar,
  wifi: IconWifi, shield: IconShield, tools: IconTools, book: IconBook, flag: IconFlag, gamepad: IconDeviceGamepad2,
  bell: IconBell, eye: IconEye, folder: IconFolder, link: IconLink, map: IconMap, screen: IconDeviceTv,
}

export function customIcon(name: string): Icon {
  return CUSTOM_ICONS[name] ?? IconFolder
}

/** The icon of a row in an admin's section: the page's own, or one for a dashboard or an address. */
export function linkIcon(link: CustomLink): Icon {
  if (link.kind === 'page' && link.page) return pageIcon(link.page)
  if (link.kind === 'dashboard') return IconLayoutDashboard
  return link.external ? IconExternalLink : IconLink
}

export interface Grouped {
  pinned: NavPage[]
  sections: { id: SectionId; pages: NavPage[] }[]
}

/** The server's list sorted into the sidebar: pinned first, then sections in their order, empty ones left out. */
export function group(pages: NavPage[]): Grouped {
  const byId = new Map(pages.map((p) => [p.id, p]))
  const pick = (ids: string[]) => ids.flatMap((id) => byId.get(id) ?? [])
  const known = new Set([...PINNED, ...SECTIONS.flatMap((s) => s.pages)])
  const sections = SECTIONS.map((s) => ({ id: s.id, pages: pick(s.pages) }))
  sections.push({ id: 'plugins', pages: pages.filter((p) => isPluginPage(p.id)) })
  sections.push({ id: 'more', pages: pages.filter((p) => !known.has(p.id) && !isPluginPage(p.id)) })
  return { pinned: pick(PINNED), sections: sections.filter((s) => s.pages.length > 0) }
}

/** Is ``href`` the page at ``path``? Sub pages (/incidents/qr) count for their parent unless the
 *  parent is "/" or has its own entry, so exactly one row is lit. */
export function activeHref(pages: { href: string }[], path: string): string | null {
  let best: string | null = null
  for (const p of pages) {
    const hit = p.href === path || (p.href !== '/' && path.startsWith(p.href + '/'))
    if (hit && (!best || p.href.length > best.length)) best = p.href
  }
  return best
}

/** Pages Flask still draws itself: a full page load. Everything else in the list is a route of the
 *  React app, so the sidebar stays put and only the page changes. */
const SERVER_PAGES = new Set(['/', '/kiosk'])

export function isServerPage(href: string): boolean {
  const path = href.split(/[?#]/)[0]
  return SERVER_PAGES.has(path) || path.startsWith('/api/') || path.startsWith('/static/')
}

/** Can ``href`` open as a route of the React app? Not a page Flask draws, and not a big-screen or
 *  print view (the server picks their theme). With ``listed``, only pages in the sidebar's list. */
export function inApp(href: string, listed?: Set<string>): boolean {
  const url = new URL(href, 'http://x')
  if (isServerPage(url.pathname) || url.searchParams.has('screen') || url.searchParams.has('print')) return false
  return !listed || listed.has(url.pathname)
}
