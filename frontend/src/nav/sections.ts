import {
  IconAlertTriangle, IconApps, IconArchive, IconArmchair, IconArrowsExchange, IconBackpack, IconBolt, IconBook,
  IconBroadcast, IconCalendar, IconCalendarEvent, IconChartLine, IconChartPie, IconChecklist, IconClipboardCheck,
  IconDeviceGamepad2, IconFileText, IconGauge, IconHeartbeat, IconHistory, IconKey, IconLayoutDashboard, IconLayoutGrid,
  IconHeadset, IconHierarchy2, IconLifebuoy, IconListSearch, IconLock, IconLogin, IconNetwork, IconPlayerPlay, IconPlug, IconPlugConnected, IconPuzzle, IconReport,
  IconServer, IconServer2, IconServerBolt, IconSettings, IconShield, IconTableOptions, IconTemplate, IconTerminal, IconTerminal2, IconToggleRight,
  IconTools, IconTournament, IconTrophy, IconUserCheck, IconUsers, IconUsersGroup, IconWall, IconWebhook, IconWifi, IconWorldWww,
  type Icon,
} from '@tabler/icons-react'

/** A page as the server lists it (GET /api/pages, floorbit/page_index.py): only those this account may open. */
export interface NavPage { href: string; id: string; label: string }

export type SectionId = 'helpdesk' | 'network' | 'build' | 'event' | 'admin' | 'more'

/** The pages crews open all the time: always at the top of the sidebar, never folded away. */
export const PINNED = ['floorPlan', 'seats', 'dashboard', 'problems', 'incidents']

/** The rest, folded into sections. A page the server lists that isn't here lands in "more",
 *  so a new page shows up before anyone sorts it in. */
export const SECTIONS: { id: SectionId; icon: Icon; pages: string[] }[] = [
  { id: 'helpdesk', icon: IconHeadset, pages: ['jobs', 'handover', 'runbooks', 'checkins', 'speedtests', 'networkStatus'] },
  {
    id: 'network', icon: IconNetwork,
    pages: ['health', 'topology', 'firewalls', 'services', 'stats', 'traffic', 'dns', 'games', 'gameServers', 'logs', 'security', 'wifi', 'power', 'commands', 'terminal'],
  },
  { id: 'build', icon: IconTools, pages: ['inventory', 'seatMapping', 'cables', 'gear', 'preflight', 'templates'] },
  { id: 'event', icon: IconCalendarEvent, pages: ['tournament', 'brackets', 'schedule', 'timeline', 'replay', 'report', 'events'] },
  { id: 'admin', icon: IconSettings, pages: ['settings', 'plugins', 'features', 'apiTokens', 'agents', 'webhooks', 'switchLogins', 'users', 'teams', 'signIn', 'audit'] },
]

const ICONS: Record<string, Icon> = {
  floorPlan: IconLayoutGrid, seats: IconArmchair, dashboard: IconLayoutDashboard, problems: IconAlertTriangle,
  incidents: IconLifebuoy, jobs: IconClipboardCheck, handover: IconArrowsExchange, runbooks: IconBook,
  checkins: IconUserCheck, speedtests: IconGauge, networkStatus: IconBroadcast, health: IconHeartbeat, stats: IconChartLine, traffic: IconChartPie,
  dns: IconWorldWww, games: IconDeviceGamepad2, gameServers: IconServer2, topology: IconHierarchy2, firewalls: IconWall, services: IconServerBolt, logs: IconFileText, security: IconShield, wifi: IconWifi, power: IconBolt,
  commands: IconTerminal2, terminal: IconTerminal, inventory: IconServer, seatMapping: IconTableOptions, cables: IconPlug,
  gear: IconBackpack, preflight: IconChecklist, templates: IconTemplate,
  tournament: IconTrophy, brackets: IconTournament, schedule: IconCalendar, timeline: IconHistory, replay: IconPlayerPlay,
  report: IconReport, events: IconArchive, settings: IconSettings, plugins: IconPuzzle, features: IconToggleRight,
  apiTokens: IconKey, agents: IconPlugConnected, webhooks: IconWebhook, switchLogins: IconLock, users: IconUsers, teams: IconUsersGroup, signIn: IconLogin, audit: IconListSearch,
}

export function pageIcon(id: string): Icon {
  return ICONS[id] ?? IconApps
}

export function sectionIcon(id: SectionId): Icon {
  return SECTIONS.find((s) => s.id === id)?.icon ?? IconApps
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
  sections.push({ id: 'more', pages: pages.filter((p) => !known.has(p.id)) })
  return { pinned: pick(PINNED), sections: sections.filter((s) => s.pages.length > 0) }
}

/** Is ``href`` the page at ``path``? Sub pages (/incidents/qr) count for their parent unless the
 *  parent is "/" or has its own entry, so exactly one row is lit. */
export function activeHref(pages: NavPage[], path: string): string | null {
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
