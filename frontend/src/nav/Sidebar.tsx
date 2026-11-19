import {
  IconChevronDown, IconDots, IconStar, IconStarFilled, IconLanguage, IconLayoutSidebarLeftCollapse, IconLayoutSidebarLeftExpand, IconLogout,
  IconBuildingCommunity, IconMenu2, IconMoon, IconSearch, IconSelector, IconSettings, IconSun, IconX, type Icon,
} from '@tabler/icons-react'
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toggleScheme, useScheme } from '@/colorScheme'
import { LANGUAGES, setLang, type Lang } from '@/i18n/lang'
import { fetchOtherTenants, readFolded, readRail, saveFolded, saveRail, useNavPrefs, switchTenant, type NavBoot, type NavPrefs, type OtherTenant } from './boot'
import { useCloseOutside } from './closeOutside'
import { EventPicker } from './EventPicker'
import './nav.css'
import { activeHref, boardHref, group, HUBS, isPluginPage, linkIcon, pageIcon, rowsOf, TABS, withParents, type CustomLink, type NavPage } from './sections'

export interface LinkProps {
  href: string
  className: string
  title?: string
  'aria-label'?: string
  'aria-current'?: 'page'
  onClick?: (e: MouseEvent) => void
  children: ReactNode
}

/** An extra entry in the account menu (the React pages add notifications and the crew notice). */
export interface MenuAction { id: string; label: string; icon: Icon; run: () => void }

export interface SidebarProps {
  boot: NavBoot
  /** The path on screen, to light its row. */
  path: string
  /** A route link inside the React app, a plain link on the server pages. */
  renderLink: (p: LinkProps) => ReactNode
  onGoTo: () => void
  /** The dashboards this account sees, for the ones pinned to the sidebar. */
  dashboards?: { id: string; name: string }[]
  /** Switches down right now, next to Problems; null while unknown. */
  down?: number | null
  actions?: MenuAction[]
}

const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

function initials(name: string) {
  return name.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('') || '?'
}

/** The one navigation of every crew page (issue: "move it all to a small sidebar"): a sidebar that
 *  folds to icons on a desktop, a bar at the bottom and a menu sheet on a phone. */
// Keyboard users would otherwise tab through every sidebar link on each page.
// Focus <main> itself, so Layout needs no id and the next Tab starts in the page.
function skipToMain(e: MouseEvent<HTMLAnchorElement>) {
  const main = document.querySelector('main')
  if (!main) return
  e.preventDefault()
  main.setAttribute('tabindex', '-1')
  main.focus()
}

export function Sidebar(props: SidebarProps) {
  const { t } = useTranslation()
  const [rail, setRail] = useState(readRail)
  const [prefs, setPrefs] = useNavPrefs(props.boot)
  // Remembers the page it opened on: a link (a new page) closes it without an effect.
  const [sheetAt, setSheetAt] = useState<string | null>(null)
  const sheet = sheetAt === props.path
  const setSheet = (open: boolean) => setSheetAt(open ? props.path : null)
  // A tab of another page (Users in Settings) lights its page's row.
  const lit = activeHref([...rowsOf(props.boot.pages), ...pinnedBoards(props.dashboards).filter((b) => prefs.favourites.includes(b.id)), ...(props.boot.custom ?? []).flatMap((c) => c.links)], props.path)

  useEffect(() => {
    if (!sheet) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSheetAt(null) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [sheet])

  const toggleRail = () => {
    setRail((r) => {
      saveRail(!r)
      return !r
    })
  }

  // Phone bar: the four pages crews open most, then everything else behind "Menu".
  const byId = new Map(withParents(props.boot.pages).map((p) => [p.id, p]))
  const tabs = TABS.flatMap((id) => byId.get(id) ?? []).slice(0, 4)
  return (
    <>
      <a className="fb-skip" href="#main" onClick={skipToMain}>{t('nav.skip')}</a>
      <nav className="fb-nav" data-state={rail ? 'rail' : 'full'} aria-label={t('nav.label')}>
        <Panel {...props} rail={rail} lit={lit} onToggleRail={toggleRail} prefs={prefs} setPrefs={setPrefs} />
      </nav>

      <nav className="fb-tabbar" aria-label={t('nav.quick')}>
        {tabs.map((p) => {
          const Icon = pageIcon(p.id)
          return (
            <span key={p.href} className="fb-tabbar-cell">
              {props.renderLink({
                href: p.href,
                className: 'fb-tabbar-item',
                'aria-current': lit === p.href ? 'page' : undefined,
                children: (
                  <>
                    <span className="fb-tabbar-icon">
                      <Icon size={22} aria-hidden="true" />
                      {(p.id === 'helpdesk' || p.id === 'problems') && !!props.down && <span className="fb-nav-dot" aria-hidden="true" />}
                    </span>
                    <span className="fb-tabbar-label">{t(`goto.pages.${p.id}`, { defaultValue: p.label })}</span>
                  </>
                ),
              })}
            </span>
          )
        })}
        <span className="fb-tabbar-cell">
          <button type="button" className="fb-tabbar-item" aria-expanded={sheet} aria-controls="fb-sheet" onClick={() => setSheet(true)}>
            <span className="fb-tabbar-icon"><IconMenu2 size={22} aria-hidden="true" /></span>
            <span className="fb-tabbar-label">{t('nav.menu')}</span>
          </button>
        </span>
      </nav>

      {sheet && (
        <div className="fb-sheet-backdrop" onClick={() => setSheet(false)}>
          <div
            id="fb-sheet" className="fb-sheet" role="dialog" aria-modal="true" aria-label={t('nav.menu')}
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" className="fb-nav-icon-btn fb-sheet-close" onClick={() => setSheet(false)} aria-label={t('nav.closeMenu')}>
              <IconX size={20} aria-hidden="true" />
            </button>
            <Panel {...props} rail={false} lit={lit} onGoTo={() => { setSheet(false); props.onGoTo() }} sheet prefs={prefs} setPrefs={setPrefs} />
          </div>
        </div>
      )}
    </>
  )
}

interface PanelProps extends SidebarProps {
  rail: boolean
  lit: string | null
  onToggleRail?: () => void
  sheet?: boolean
  prefs: NavPrefs
  setPrefs: (p: NavPrefs) => void
}

function Panel(props: PanelProps) {
  const { t } = useTranslation()
  const { boot, rail, lit, prefs } = props
  const { pinned, sections } = group(boot.pages)
  // Settings sits at the foot, next to the account (issue #892).
  const settings = rowsOf(boot.pages).find((p) => p.id === 'settings')
  const byId = new Map([...withParents(boot.pages), ...pinnedBoards(props.dashboards)].map((p) => [p.id, p]))
  const favourites = prefs.favourites.map((id) => byId.get(id)).filter((p): p is NavPage => !!p)
  const [folded, setFolded] = useState<string[]>(readFolded)
  const isFav = (id: string) => prefs.favourites.includes(id)
  const toggleFav = (id: string) =>
    props.setPrefs({ ...prefs, favourites: isFav(id) ? prefs.favourites.filter((x) => x !== id) : [...prefs.favourites, id] })

  const row = (p: NavPage, star = !rail) => {
    const Icon = pageIcon(p.id, p.icon)
    const label = ownLabel(p.id) ? p.label : t(`goto.pages.${p.id}`, { defaultValue: p.label })
    const badge = (p.id === 'helpdesk' || p.id === 'problems') && props.down ? props.down : null
    const fav = isFav(p.id)
    return (
      <li key={p.href} className="fb-nav-item">
        {props.renderLink({
          href: p.href,
          className: 'fb-nav-row',
          title: rail ? label : undefined,
          'aria-current': lit === p.href ? 'page' : undefined,
          children: (
            <>
              <Icon size={18} className="fb-nav-icon" aria-hidden="true" />
              <span className="fb-nav-text">{label}</span>
              {badge !== null && (
                <span className="fb-nav-badge" title={t('nav.problemsDown', { count: badge })}>
                  <span className="fb-sr-only">{t('nav.problemsDown', { count: badge })}</span>
                  <span aria-hidden="true">{badge}</span>
                </span>
              )}
            </>
          ),
        })}
        {star && (
          <button
            type="button" className="fb-nav-fav" aria-pressed={fav} onClick={() => toggleFav(p.id)}
            aria-label={t(fav ? 'nav.favRemove' : 'nav.favAdd', { page: label })} title={t(fav ? 'nav.favRemove' : 'nav.favAdd', { page: label })}
          >
            {fav ? <IconStarFilled size={14} aria-hidden="true" /> : <IconStar size={14} aria-hidden="true" />}
          </button>
        )}
      </li>
    )
  }

  // An admin's own section: an address on another site opens in a new tab, past the app's router.
  const customRow = (x: CustomLink) => {
    const Icon = linkIcon(x)
    const label = x.kind === 'page' && x.page && !x.own ? t(`goto.pages.${x.page}`, { defaultValue: x.label }) : x.label
    const children = (
      <>
        <Icon size={18} className="fb-nav-icon" aria-hidden="true" />
        <span className="fb-nav-text">{label}</span>
      </>
    )
    const common = { className: 'fb-nav-row', title: rail ? label : undefined, 'aria-current': lit === x.href ? 'page' as const : undefined }
    return (
      <li key={`${x.kind}:${x.href}`} className="fb-nav-item">
        {x.external
          ? <a href={x.href} target="_blank" rel="noopener noreferrer" {...common}>{children}</a>
          : props.renderLink({ href: x.href, ...common, children })}
      </li>
    )
  }

  // The admins' own sections first (ids "c:<id>", so they never meet a built-in one), then Floorbit's.
  const groups = [
    ...(boot.custom ?? []).map((c) => ({
      id: `c:${c.id}`, label: c.name, custom: true, hrefs: c.links.map((x) => x.href),
      rows: () => c.links.map(customRow),
    })),
    ...sections.map((s) => ({
      id: s.id as string, label: t(`nav.sections.${s.id}`), custom: false, hrefs: s.pages.map((p) => p.href),
      rows: (star: boolean) => s.pages.map((p) => row(p, star)),
    })),
  ]
  const litSection = groups.find((s) => s.hrefs.some((h) => h === lit))?.id
  // A group with the page on screen is always open; the rest stay as someone left them.
  const isOpen = (id: string) => id === litSection || !folded.includes(id)
  const toggle = (id: string) => {
    const next = isOpen(id) ? [...folded, id] : folded.filter((x) => x !== id)
    setFolded(next)
    saveFolded(next)
  }
  return (
    <>
      <div className="fb-nav-top">
        {props.renderLink({
          href: '/', className: 'fb-nav-brand', title: t('nav.home'),
          children: <Brand boot={boot} rail={rail} />,
        })}
      </div>

      <EventPicker rail={rail} sheet={props.sheet} pages={HUBS.event.flatMap((id) => boot.pages.find((p) => p.id === id) ?? [])} />

      <button type="button" className="fb-nav-row fb-nav-search" onClick={props.onGoTo} title={rail ? t('nav.goTo') : undefined} aria-keyshortcuts="Control+K Meta+K">
        <IconSearch size={18} className="fb-nav-icon" aria-hidden="true" />
        <span className="fb-nav-text">{t('nav.goTo')}</span>
        <kbd className="fb-nav-kbd">{mac ? '⌘K' : 'Ctrl K'}</kbd>
      </button>

      <div className="fb-nav-scroll">
        {favourites.length > 0 && (
          <div className="fb-nav-favs">
            {!rail && <div className="fb-nav-group-label">{t('nav.favourites')}</div>}
            <ul className="fb-nav-list" aria-label={t('nav.favourites')}>{favourites.map((p) => row(p))}</ul>
          </div>
        )}
        <ul className="fb-nav-list">{pinned.map((p) => row(p))}</ul>
        {groups.map((s) => {
          // Folded to icons, every group shows its pages' icons, with a line between groups.
          const expanded = rail || isOpen(s.id)
          return (
            <div key={s.id} className={s.custom ? 'fb-nav-section fb-nav-custom' : 'fb-nav-section'} data-lit={s.id === litSection || undefined}>
              {!rail && (
                <button
                  type="button" className="fb-nav-section-head" aria-expanded={expanded}
                  onClick={() => toggle(s.id)}
                >
                  <span className="fb-nav-text">{s.label}</span>
                  <IconChevronDown size={13} className="fb-nav-chevron" aria-hidden="true" />
                </button>
              )}
              {expanded && <ul className="fb-nav-list fb-nav-sub" aria-label={rail ? s.label : undefined}>{s.rows(!rail)}</ul>}
            </div>
          )
        })}
      </div>

      <Tenants {...props} />
      <div className="fb-nav-foot">
        <Account {...props} />
        {settings && props.renderLink({
          href: settings.href, className: 'fb-nav-icon-btn fb-nav-settings', title: t('goto.pages.settings'),
          'aria-label': t('goto.pages.settings'), 'aria-current': lit === settings.href ? 'page' : undefined,
          children: <IconSettings size={18} aria-hidden="true" />,
        })}
        {props.onToggleRail && (
          <button
            type="button" className="fb-nav-icon-btn fb-nav-fold" onClick={props.onToggleRail}
            aria-label={rail ? t('nav.expand') : t('nav.collapse')} title={rail ? t('nav.expand') : t('nav.collapse')}
          >
            {rail ? <IconLayoutSidebarLeftExpand size={18} aria-hidden="true" /> : <IconLayoutSidebarLeftCollapse size={18} aria-hidden="true" />}
          </button>
        )}
      </div>
    </>
  )
}

/** A plugin's page or a pinned dashboard names itself; Floorbit's pages have their texts. */
const ownLabel = (id: string) => isPluginPage(id) || id.startsWith('dashboard:')

/** Every dashboard as a row that can be pinned (``dashboard:<id>`` in the favourites). */
function pinnedBoards(dashboards: { id: string; name: string }[] | undefined): NavPage[] {
  return (dashboards ?? []).map((d) => ({ href: boardHref(d.id), id: `dashboard:${d.id}`, label: d.name }))
}

function Brand({ boot, rail }: { boot: NavBoot; rail: boolean }) {
  // The same choice as templates/_brand.html: an event logo, an event name, or Floorbit's lockup.
  if (boot.brand.logo) return <img className="fb-nav-logo" src={boot.brand.logo} alt={boot.brand.name || 'Event logo'} />
  if (rail || boot.brand.name) {
    return (
      <span className="fb-brand">
        <span className="fb-brand-mark" role="img" aria-label="Floorbit" />
        {!rail && boot.brand.name && <span className="fb-brand-name">{boot.brand.name}</span>}
      </span>
    )
  }
  return <span className="fb-brand"><span className="fb-brand-lockup" role="img" aria-label="Floorbit" /></span>
}

/** The tenant switcher: only there when this person can reach another tenant of the platform. */
function Tenants(props: PanelProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [list, setList] = useState<OtherTenant[] | null>(null)
  const [going, setGoing] = useState<string | null>(null)
  const [error, setError] = useState('')
  const box = useRef<HTMLDivElement>(null)
  const ask = !!props.boot.tenants && !!props.boot.user && !props.boot.user.platform
  useCloseOutside(open, setOpen, box)

  useEffect(() => {
    if (!ask) return
    let live = true
    void fetchOtherTenants().then((found) => { if (live) setList(found) })
    return () => { live = false }
  }, [ask])

  if (!list?.length) return null
  const here = props.boot.brand.name || t('nav.thisTenant')
  const go = (o: OtherTenant) => {
    setGoing(o.id)
    setError('')
    switchTenant(o.id)
      .then((url) => { window.location.assign(url) })
      .catch((e: unknown) => { setGoing(null); setError(e instanceof Error ? e.message : String(e)) })
  }
  return (
    <div className="fb-nav-account fb-nav-tenants" ref={box}>
      <button
        type="button" className="fb-nav-row fb-nav-tenant" aria-expanded={open} aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)} title={props.rail ? t('nav.switchTenant') : undefined}
        aria-label={props.rail ? t('nav.switchTenant') : undefined}
      >
        <IconBuildingCommunity size={18} className="fb-nav-icon" aria-hidden="true" />
        <span className="fb-nav-text">{here}</span>
        <IconSelector size={14} className="fb-nav-tenant-mark" aria-hidden="true" />
      </button>
      {open && (
        <div className="fb-nav-menu" role="menu" data-sheet={props.sheet || undefined}>
          <div className="fb-nav-menu-label">{t('nav.switchTenant')}</div>
          {list.map((o) => (
            <button key={o.id} type="button" role="menuitem" className="fb-nav-menu-item" disabled={!!going} onClick={() => go(o)}>
              <span className="fb-nav-tenant-name">{o.name || o.id}</span>
              <span className="fb-nav-tenant-how">{going === o.id ? t('nav.switching') : o.how === 'platform' ? t('nav.asPlatform') : ''}</span>
            </button>
          ))}
          {error && <div className="fb-nav-menu-label" role="alert">{error}</div>}
        </div>
      )}
    </div>
  )
}

function Account(props: PanelProps) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const scheme = useScheme()
  const toggle = toggleScheme()
  const user = props.boot.user
  useCloseOutside(open, setOpen, box)

  const name = user ? user.name || user.username : t('nav.account')
  const run = (f: () => void) => () => { setOpen(false); f() }
  return (
    <div className="fb-nav-account" ref={box}>
      <button
        type="button" className="fb-nav-row fb-nav-me" aria-expanded={open} aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)} title={props.rail ? name : undefined}
        // In the rail only the avatar shows, so the button needs a label. Expanded, the button reads
        // its name from its text, not from an aria-label that hides the name on screen.
        aria-label={props.rail ? (user ? t('common.signedInAs', { username: user.username }) : t('nav.account')) : undefined}
      >
        <span className="fb-nav-avatar" aria-hidden="true">{user ? initials(name) : <IconDots size={16} />}</span>
        {user && !props.rail && <span className="fb-sr-only">{t('common.signedInAs', { username: user.username })}</span>}
        <span className="fb-nav-text" aria-hidden={user && !props.rail ? true : undefined}>{name}</span>
      </button>
      {open && (
        <div className="fb-nav-menu" role="menu" data-sheet={props.sheet || undefined}>
          {user && <div className="fb-nav-menu-label">{t('common.signedInAs', { username: user.username })}</div>}
          {user?.platform && <div className="fb-nav-menu-label">{t('nav.platformVisit')}</div>}
          <div className="fb-nav-menu-label"><IconLanguage size={14} aria-hidden="true" /> {t('common.language')}</div>
          {LANGUAGES.map((l) => (
            <button
              key={l.code} type="button" role="menuitemradio" aria-checked={i18n.language === l.code} lang={l.code}
              className="fb-nav-menu-item" onClick={run(() => setLang(l.code as Lang))}
            >
              {l.label}
            </button>
          ))}
          <hr />
          {toggle && (
            <>
              <hr />
              <button type="button" role="menuitem" className="fb-nav-menu-item" onClick={run(toggle)}>
                {scheme === 'light' ? <IconMoon size={16} aria-hidden="true" /> : <IconSun size={16} aria-hidden="true" />}
                {scheme === 'light' ? t('common.themeDark') : t('common.themeLight')}
              </button>
            </>
          )}
          {!!props.actions?.length && <hr />}
          {props.actions?.map((a) => (
            <button key={a.id} type="button" role="menuitem" className="fb-nav-menu-item" onClick={run(a.run)}>
              <a.icon size={16} aria-hidden="true" /> {a.label}
            </button>
          ))}
          {props.boot.signOut && user && (
            <>
              <hr />
              <form method="post" action="/logout">
                <button type="submit" role="menuitem" className="fb-nav-menu-item">
                  <IconLogout size={16} aria-hidden="true" /> {t('common.signOut')}
                </button>
              </form>
            </>
          )}
        </div>
      )}
    </div>
  )
}
