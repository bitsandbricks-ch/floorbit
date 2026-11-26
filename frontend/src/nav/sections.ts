import {
  IconActivityHeartbeat, IconApps, IconArmchair, IconBell, IconBolt, IconBook, IconCalendar, IconChartLine,
  IconDeviceGamepad2, IconDeviceTv, IconExternalLink, IconEye, IconFlag, IconFolder, IconHeart,
  IconLayoutDashboard, IconLifebuoy, IconLink, IconMap, IconNetwork, IconPuzzle, IconServer, IconShield,
  IconStar, IconTools, IconTrophy, IconUsers, IconWifi, type Icon,
} from '@tabler/icons-react'

/** A page as the server lists it (GET /api/pages, floorbit/page_index.py): only those this account may open. */
export interface NavPage {
  href: string; id: string; label: string
  /** A plugin's page (id ``plugin:<plugin>:<page>``): the plugin's icon name, and its label as the plugin gives it. */
  icon?: string
  /** A row that bundles tabs (Helpdesk): the tabs' addresses, which light this row too. */
  also?: string[]
}

export type SectionId = 'work' | 'monitoring' | 'places' | 'tools' | 'screens' | 'plugins' | 'more'

/** A plugin's own page (plugin.yaml ``pages:``), which goes into the Plugins section. */
export const isPluginPage = (id: string) => id.startsWith('plugin:')

/** The start pages: always at the top of the sidebar, above the groups. Events has its row here
 *  (issue #1201); the picker above only switches the event. */
export const PINNED = ['overview', 'floorPlan', 'events']

/** The phone's bottom bar: the pages crews open most; everything else is behind "Menu". */
export const TABS = ['overview', 'floorPlan', 'helpdesk', 'services']

/** The groups, in the sidebar's order (issue #892): about a dozen rows, the work that comes in
 *  first. Most rows bundle several pages as tabs (HUBS). A page the server lists that is in
 *  neither lands in "more", so a new page shows up before anyone sorts it in. */
export const SECTIONS: { id: SectionId; icon: Icon; pages: string[] }[] = [
  { id: 'work', icon: IconLifebuoy, pages: ['helpdesk'] },
  { id: 'monitoring', icon: IconActivityHeartbeat, pages: ['network', 'services', 'traffic', 'agents'] },
  { id: 'places', icon: IconArmchair, pages: ['seats', 'inventory'] },
  { id: 'tools', icon: IconTools, pages: ['console', 'logs'] },
  { id: 'screens', icon: IconDeviceTv, pages: ['dashboards'] },
]

/** One area of the sidebar (``src/nav/areas/<area>.ts``): its row, the pages it holds as tabs,
 *  and their icons. A new area is a new file there, so pull requests don't all edit one list. */
export interface NavArea {
  /** The row that bundles ``tabs``; none for pages that are only listed for their icon. */
  hub?: string
  tabs?: string[]
  icons: Record<string, Icon>
}

export const AREAS: NavArea[] = Object.values(
  import.meta.glob<NavArea>('./areas/*.ts', { eager: true, import: 'area' }),
)

/** Rows that hold other pages as tabs (issue #892). A row is a page of its own (Inventory,
 *  Settings) or only a bundle (Helpdesk): then it opens its first tab this account may open.
 *  The tabs show under the top bar (HubTabs); Settings draws its own. "Go to" still finds every
 *  page. */
export const HUBS: Record<string, string[]> = Object.fromEntries(
  AREAS.flatMap((a) => (a.hub ? [[a.hub, a.tabs ?? []]] : [])),
)

/** Hubs that draw their tabs themselves (pages/Settings.tsx). */
export const OWN_TABS = ['settings']

/** Rows outside the sidebar's groups: Settings sits at the foot, the checks before doors open
 *  are a panel on Set up (#1049) and the topology a view of the floor plan (#1330), which "Go to"
 *  still finds. */
export const OFF_LIST = ['settings', 'setup', 'preflight', 'topology']

/** Pages that are a tab of another row: page -> its row. */
export const INSIDE: Record<string, string> = Object.fromEntries(
  Object.entries(HUBS).flatMap(([hub, ids]) => ids.map((id) => [id, hub])),
)

/** The list with each hub's row in it, lit by its tabs too. A bundle row opens its first tab
 *  this account may open; an account that may open a tab (Users) but not its row's own page
 *  (Settings) still gets the row. */
export function withParents(pages: NavPage[]): NavPage[] {
  const byId = new Map(pages.map((p) => [p.id, p]))
  const tabsOf = (hub: string) => HUBS[hub].flatMap((id) => byId.get(id) ?? [])
  const out = pages.map((p) => (HUBS[p.id] ? { ...p, also: tabsOf(p.id).map((x) => x.href) } : p))
  for (const hub of Object.keys(HUBS)) {
    const tabs = tabsOf(hub)
    if (byId.has(hub) || !tabs.length) continue
    out.push({ href: tabs[0].href, id: hub, label: hub, also: tabs.slice(1).map((x) => x.href) })
  }
  return out
}

/** The sidebar's rows: hubs in, their tabs out. */
export const rowsOf = (pages: NavPage[]) => withParents(pages).filter((p) => !(p.id in INSIDE))

/** The tabs of the row the page at ``path`` belongs to: the row's own page first, then its tabs
 *  this account may open. Null when the row has none, or only one. */
export function hubTabs(pages: NavPage[], path: string): { hub: string; tabs: NavPage[] } | null {
  const rows = rowsOf(pages)
  const lit = activeHref(rows, path)
  const row = rows.find((p) => p.href === lit)
  if (!row || !HUBS[row.id] || OWN_TABS.includes(row.id)) return null
  const byId = new Map(pages.map((p) => [p.id, p]))
  const tabs = [...(byId.has(row.id) ? [byId.get(row.id)!] : []), ...HUBS[row.id].flatMap((id) => byId.get(id) ?? [])]
  return tabs.length > 1 ? { hub: row.id, tabs } : null
}

/** Groups folded until someone opens them (or a page in them is on screen): what the person put
 *  away under "More" (the shared NAV_MORE). */
export const FOLDED: string[] = ['_more']

const ICONS: Record<string, Icon> = Object.assign({}, ...AREAS.map((a) => a.icons))

/** A dashboard inside the app's frame, with the sidebar (``/dashboards/<id>`` is the big screen). */
export const boardHref = (id: string) => `/dashboards/view/${encodeURIComponent(id)}`

export function pageIcon(id: string, icon?: string): Icon {
  if (id.startsWith('dashboard:')) return IconLayoutDashboard
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
export function group(all: NavPage[]): Grouped {
  const pages = rowsOf(all)
  const byId = new Map(pages.map((p) => [p.id, p]))
  const pick = (ids: string[]) => ids.flatMap((id) => byId.get(id) ?? [])
  const known = new Set([...PINNED, ...OFF_LIST, ...SECTIONS.flatMap((s) => s.pages)])
  const sections = SECTIONS.map((s) => ({ id: s.id, pages: pick(s.pages) }))
  sections.push({ id: 'plugins', pages: pages.filter((p) => isPluginPage(p.id)) })
  sections.push({ id: 'more', pages: pages.filter((p) => !known.has(p.id) && !isPluginPage(p.id)) })
  return { pinned: pick(PINNED), sections: sections.filter((s) => s.pages.length > 0) }
}

/** Is ``href`` the page at ``path``? Sub pages (/incidents/qr) count for their parent unless the
 *  parent is "/" or has its own entry, so exactly one row is lit. */
export function activeHref(pages: { href: string; also?: string[] }[], path: string): string | null {
  let best: string | null = null
  let bestLen = 0
  for (const p of pages) {
    // A hub's row is lit by its tabs too; the longest address that holds the path wins.
    for (const href of [p.href, ...(p.also ?? [])]) {
      const hit = href === path || (href !== '/' && path.startsWith(href + '/'))
      if (hit && href.length > bestLen) { best = p.href; bestLen = href.length }
    }
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
