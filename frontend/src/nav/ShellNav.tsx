import { UnstyledButton } from '@mantine/core'
import { IconLayoutSidebar, IconStar, IconStarFilled } from '@tabler/icons-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { NAV_FAVOURITES, NAV_MORE, NavCustomizer, PhoneDock, toggleNavPin, useCustomNav, type NavGroup, type NavItem, type NavSection } from '@bitsandbricks/ui'
import { readFolded, readRail, saveFolded, saveRail, useNavPrefs, type NavBoot } from './boot'
import { EventPicker } from './EventPicker'
import { Account, Brand, Tenants, type MenuAction } from './NavParts'
import './nav.css'
import { activeHref, boardHref, group, INSIDE, isPluginPage, linkIcon, pageIcon, rowsOf, TABS, withParents, type CustomLink, type NavPage } from './sections'

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
 *  groups, the tenant switcher and account menu at the foot, folding to icons, and the phone's
 *  bottom bar. The groups are Floorbit's own sidebar (the start pages, the admins' sections,
 *  Floorbit's sections, Plugins and Settings) as the person arranged it with the shared NavPrefs
 *  (#1597): their favourites on top, their own categories, what they put away under "More".
 *  The admins' sections and the foot stay where they are (locked). */
export function useShellNav(props: ShellNavProps) {
  const { t } = useTranslation()
  const { boot, path } = props
  const [folded, setFolded] = useState(readRail)
  const [prefs, setPrefs] = useNavPrefs(boot)
  const [customising, setCustomising] = useState(false)
  const [closed, setClosed] = useState<string[]>(readFolded)
  const pins = prefs.pinned ?? []
  // A dashboard is in the sidebar only while it is pinned (from its page or the Dashboards table).
  const boards = pinnedBoards(props.dashboards).filter((b) => pins.includes(b.id))
  const custom = boot.custom ?? []
  // A tab of another page (Users in Settings) lights its page's row.
  const lit = activeHref([...rowsOf(boot.pages), ...boards, ...custom.flatMap((c) => c.links)], path)
  const byId = new Map([...withParents(boot.pages), ...boards].map((p) => [p.id, p]))
  const { pinned, sections } = group(boot.pages)

  const onFoldedChange = (next: boolean) => {
    saveRail(next)
    setFolded(next)
  }

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
  // Every entry once, by its page id: the shared prefs pin, move and put away entries by id.
  const item = (p: NavPage, opts: { star?: boolean; active?: boolean } = {}): NavItem => {
    const Icon = pageIcon(p.id, p.icon)
    const label = labelOf(p)
    const fav = pins.includes(p.id)
    return {
      id: p.id, label, href: p.href, icon: <Icon size={18} />,
      active: opts.active ?? lit === p.href, badge: badgeOf(p.id),
      action: opts.star === false ? undefined : (
        <UnstyledButton
          className="fb-nav-fav" aria-pressed={fav} onClick={() => setPrefs(toggleNavPin(prefs, p.id))}
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

  // Floorbit's own sidebar, before the person's prefs: the start pages (no heading), the admins'
  // sections (ids "c:<id>", locked: the admin arranges those), Floorbit's sections, the foot.
  const own: NavSection[] = [
    { id: 'start', items: pinned.map((p) => item(p)) },
    ...custom.map((c) => ({ id: `c:${c.id}`, label: c.name, items: c.links.map(customItem), locked: true })),
    ...sections.map((s) => ({ id: s.id as string, label: t(`nav.sections.${s.id}`), items: s.pages.map((p) => item(p)) })),
    ...(admin.length ? [{ id: 'admin', items: admin.map((p) => item(p, { star: false, active: p.id === adminLit })), locked: true }] : []),
  ]
  // A pinned page that is no row of its own (a dashboard, or a tab such as Problems that someone
  // pinned before rows bundled tabs) joins the group of the row it belongs to, so the pin keeps it.
  const rows = new Set(own.flatMap((g) => g.items.map((i) => i.id)))
  for (const id of pins) {
    const p = byId.get(id)
    if (!p || rows.has(id)) continue
    const hub = id.startsWith('dashboard:') ? 'dashboards' : INSIDE[id]
    const home = own.find((g) => !g.locked && g.items.some((i) => i.id === hub)) ?? own[0]
    home.items.push(item(p))
  }
  const arranged = useCustomNav(own, prefs)

  const toggle = (id: string, open: boolean) => {
    const next = open ? [...closed, id] : closed.filter((x) => x !== id)
    setClosed(next)
    saveFolded(next)
  }
  const foldable = (g: NavGroup & { id: string }): NavGroup => {
    // A group with the page on screen is always open (the shell sees to that); the rest stay as someone left them.
    const open = !closed.includes(g.id)
    return { ...g, collapsible: true, open, onToggle: () => toggle(g.id, open || g.items.some((i) => i.active)) }
  }
  const fixed = new Set([NAV_FAVOURITES, 'start', 'admin'])
  const groups: NavGroup[] = arranged.nav.map((g) => (fixed.has(g.id) ? g : foldable(g)))
  // What the person put away: at the end, above the foot, folded until opened.
  if (arranged.more.length) {
    const label = arranged.groups.find((g) => g.id === NAV_MORE)?.label
    const at = groups.findIndex((g) => g.id === 'admin')
    groups.splice(at < 0 ? groups.length : at, 0, foldable({ id: NAV_MORE, label, items: arranged.more }))
  }
  const nav = groups

  const actions: MenuAction[] = [
    { id: 'customiseNav', label: t('nav.customise'), icon: IconLayoutSidebar, run: () => setCustomising(true) },
    ...(props.actions ?? []),
  ]
  // The dialog lists the entries without their stars and counts.
  const plain = own.map((s) => ({ ...s, items: s.items.map((i) => ({ ...i, action: undefined, badge: undefined, active: false })) }))
  const customizer = (
    <NavCustomizer opened={customising} onClose={() => setCustomising(false)} sections={plain} prefs={prefs} onChange={setPrefs} />
  )

  // Phone bar: the four pages crews open most, then everything else behind "More".
  const tabs = TABS.flatMap((id) => byId.get(id) ?? []).slice(0, 4)
  const litPage = [...byId.values()].find((p) => p.href === lit)
  const foot = (rail: boolean) => (
    <>
      <Tenants boot={boot} rail={rail} />
      <Account boot={boot} actions={actions} rail={rail} />
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
    customizer,
  }
}

/** A plugin's page or a pinned dashboard names itself; Floorbit's pages have their texts. */
const ownLabel = (id: string) => isPluginPage(id) || id.startsWith('dashboard:')

/** Every dashboard as a row that can be pinned (``dashboard:<id>`` in the pins). */
function pinnedBoards(dashboards: { id: string; name: string }[] | undefined): NavPage[] {
  return (dashboards ?? []).map((d) => ({ href: boardHref(d.id), id: `dashboard:${d.id}`, label: d.name }))
}
