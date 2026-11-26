import { UnstyledButton } from '@mantine/core'
import { IconStar, IconStarFilled } from '@tabler/icons-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { PhoneDock, type NavGroup, type NavItem } from '@bitsandbricks/ui'
import { readFolded, readRail, saveFolded, saveRail, useNavPrefs, type NavBoot } from './boot'
import { StatusLine } from '@/components/StatusLine'
import { EventPicker } from './EventPicker'
import { Account, Brand, Tenants, type MenuAction } from './NavParts'
import './nav.css'
import { activeHref, boardHref, group, isPluginPage, linkIcon, pageIcon, rowsOf, TABS, withParents, type CustomLink, type NavPage } from './sections'

export type { MenuAction }

export interface ShellNavProps {
  boot: NavBoot
  /** The path on screen, to light its row. */
  path: string
  /** The dashboards this account sees, for the ones pinned to the sidebar. */
  dashboards?: { id: string; name: string }[]
  /** Switches down right now, next to Problems; null while unknown. */
  down?: number | null
  /** Problems to look at (warn plus seat and port trouble), for the badge's tooltip (#884). */
  look?: number | null
  actions?: MenuAction[]
  /** The event's setup steps done of all (#1437): Set up shows at the foot while some are open. */
  setup?: { done: number; count: number } | null
}

/** What Floorbit puts into the shared AppShell: its brand, the event picker above the links, the
 *  groups (favourites, the start pages, the admins' and Floorbit's sections, Plugins and Settings),
 *  the tenant switcher and account menu at the foot, folding to icons, and the phone's bottom bar. */
export function useShellNav(props: ShellNavProps) {
  const { t } = useTranslation()
  const { boot, path } = props
  const [folded, setFolded] = useState(readRail)
  const [prefs, setPrefs] = useNavPrefs(boot)
  const [closed, setClosed] = useState<string[]>(readFolded)
  const boards = pinnedBoards(props.dashboards)
  const custom = boot.custom ?? []
  // A tab of another page (Users in Settings) lights its page's row.
  const lit = activeHref([...rowsOf(boot.pages), ...boards.filter((b) => prefs.favourites.includes(b.id)), ...custom.flatMap((c) => c.links)], path)
  const byId = new Map([...withParents(boot.pages), ...boards].map((p) => [p.id, p]))
  const { pinned, sections } = group(boot.pages)

  const onFoldedChange = (next: boolean) => {
    saveRail(next)
    setFolded(next)
  }
  const isFav = (id: string) => prefs.favourites.includes(id)
  const toggleFav = (id: string) =>
    setPrefs({ ...prefs, favourites: isFav(id) ? prefs.favourites.filter((x) => x !== id) : [...prefs.favourites, id] })

  const labelOf = (p: NavPage) => (ownLabel(p.id) ? p.label : t(`goto.pages.${p.id}`, { defaultValue: p.label }))
  const badgeOf = (id: string): ReactNode => {
    if (id === 'setup' && props.setup) {
      const { done, count } = props.setup
      return <span className="fb-nav-progress" title={t('nav.setupCount', { done, count })}>{`${done}/${count}`}</span>
    }
    const down = (id === 'helpdesk' || id === 'problems') && props.down ? props.down : null
    if (down === null) return undefined
    return (
      <span className="fb-nav-count" title={props.look ? t('nav.problemsSplit', { count: down, look: props.look }) : t('nav.problemsDown', { count: down })}>
        <span className="fb-sr-only">{t('nav.problemsDown', { count: down })}</span>
        <span aria-hidden="true">{down}</span>
      </span>
    )
  }
  const item = (p: NavPage, key: string, opts: { star?: boolean; active?: boolean } = {}): NavItem => {
    const Icon = pageIcon(p.id, p.icon)
    const label = labelOf(p)
    const fav = isFav(p.id)
    return {
      id: `${key}:${p.id}`, label, href: p.href, icon: <Icon size={18} />,
      active: opts.active ?? lit === p.href, badge: badgeOf(p.id),
      action: opts.star === false ? undefined : (
        <UnstyledButton
          className="fb-nav-fav" aria-pressed={fav} onClick={() => toggleFav(p.id)}
          aria-label={t(fav ? 'nav.favRemove' : 'nav.favAdd', { page: label })} title={t(fav ? 'nav.favRemove' : 'nav.favAdd', { page: label })}
        >
          {fav ? <IconStarFilled size={14} aria-hidden="true" /> : <IconStar size={14} aria-hidden="true" />}
        </UnstyledButton>
      ),
    }
  }
  // An admin's own section: an address on another site opens in a new tab.
  const customItem = (x: CustomLink): NavItem => {
    const Icon = linkIcon(x)
    const label = x.kind === 'page' && x.page && !x.own ? t(`goto.pages.${x.page}`, { defaultValue: x.label }) : x.label
    return { id: `${x.kind}:${x.href}`, label, href: x.href, icon: <Icon size={18} />, active: lit === x.href, external: x.external }
  }

  // Plugins and Settings sit at the foot as named rows, so they can't be missed (issue #892); Set
  // up joins them while the event's setup has open steps (#1437).
  const setupOpen = !!props.setup && props.setup.done < props.setup.count
  const admin = [...(setupOpen ? ['setup'] : []), 'plugins', 'settings'].map((id) => byId.get(id) ?? rowsOf(boot.pages).find((p) => p.id === id))
    .filter((p): p is NavPage => !!p)
  // Plugins lives under /settings, so it lights on its own pages and Settings on the rest.
  const adminLit = admin.find((p) => p.id === 'plugins' && (path === p.href || path.startsWith(`${p.href}/`)))?.id
    ?? admin.find((p) => p.href === lit)?.id
  const favourites = prefs.favourites.map((id) => byId.get(id)).filter((p): p is NavPage => !!p)

  // The admins' own sections first (ids "c:<id>", so they never meet a built-in one), then Floorbit's.
  const folding = [
    ...custom.map((c) => ({ id: `c:${c.id}`, label: c.name, items: c.links.map(customItem) })),
    ...sections.map((s) => ({ id: s.id as string, label: t(`nav.sections.${s.id}`), items: s.pages.map((p) => item(p, s.id)) })),
  ]
  const toggle = (id: string, open: boolean) => {
    const next = open ? [...closed, id] : closed.filter((x) => x !== id)
    setClosed(next)
    saveFolded(next)
  }
  const nav: NavGroup[] = [
    ...(favourites.length ? [{ id: 'favourites', label: t('nav.favourites'), items: favourites.map((p) => item(p, 'fav')) }] : []),
    { id: 'pinned', items: pinned.map((p) => item(p, 'pin')) },
    ...folding.map((g) => {
      // A group with the page on screen is always open (the shell sees to that); the rest stay as someone left them.
      const open = !closed.includes(g.id)
      return { ...g, collapsible: true, open, onToggle: () => toggle(g.id, open || g.items.some((i) => i.active)) }
    }),
    ...(admin.length ? [{ id: 'admin', items: admin.map((p) => item(p, 'admin', { star: false, active: p.id === adminLit })) }] : []),
  ]

  // Phone bar: the four pages crews open most, then everything else behind "More".
  const tabs = TABS.flatMap((id) => byId.get(id) ?? []).slice(0, 4)
  const litPage = [...byId.values()].find((p) => p.href === lit)
  const foot = (rail: boolean) => (
    <>
      <Tenants boot={boot} rail={rail} />
      <Account boot={boot} actions={props.actions} rail={rail} />
    </>
  )
  const phoneNav = (
    <PhoneDock
      items={tabs.map((p) => {
        const Icon = pageIcon(p.id)
        return { id: p.id, label: labelOf(p), href: p.href, icon: <Icon size={22} />, active: lit === p.href, badge: badgeOf(p.id) }
      })}
      more={nav.map((g) => ({ ...g, items: g.items.map((i) => ({ ...i, action: undefined })) }))}
      moreFooter={<><EventPicker rail={false} />{foot(false)}</>}
      current={litPage ? labelOf(litPage) : undefined}
      status={<StatusLine bare />}
    />
  )

  return {
    brand: (rail: boolean) => <Brand boot={boot} rail={rail} />,
    navTop: <EventPicker rail={folded} />,
    nav,
    navFooter: foot(folded),
    folded,
    onFoldedChange,
    phoneNav,
  }
}

/** A plugin's page or a pinned dashboard names itself; Floorbit's pages have their texts. */
const ownLabel = (id: string) => isPluginPage(id) || id.startsWith('dashboard:')

/** Every dashboard as a row that can be pinned (``dashboard:<id>`` in the favourites). */
function pinnedBoards(dashboards: { id: string; name: string }[] | undefined): NavPage[] {
  return (dashboards ?? []).map((d) => ({ href: boardHref(d.id), id: `dashboard:${d.id}`, label: d.name }))
}
