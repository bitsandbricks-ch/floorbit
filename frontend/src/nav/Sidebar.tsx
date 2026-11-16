import {
  IconChevronDown, IconDots, IconStar, IconStarFilled, IconLanguage, IconLayoutSidebarLeftCollapse, IconLayoutSidebarLeftExpand, IconLogout,
  IconMenu2, IconMoon, IconSearch, IconSun, IconX, type Icon,
} from '@tabler/icons-react'
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toggleScheme, useScheme } from '@/colorScheme'
import { LANGUAGES, setLang, type Lang } from '@/i18n/lang'
import { readOpen, readPrefs, readRail, saveOpen, savePrefs, saveRail, type NavBoot, type NavPrefs } from './boot'
import './nav.css'
import { activeHref, group, pageIcon, sectionIcon, type NavPage, type SectionId } from './sections'

export interface LinkProps {
  href: string
  className: string
  title?: string
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
export function Sidebar(props: SidebarProps) {
  const { t } = useTranslation()
  const [rail, setRail] = useState(readRail)
  const [prefs, setPrefsState] = useState(() => readPrefs(props.boot))
  const setPrefs = (next: NavPrefs) => {
    setPrefsState(next)
    savePrefs(props.boot, next)
  }
  // Remembers the page it opened on: a link (a new page) closes it without an effect.
  const [sheetAt, setSheetAt] = useState<string | null>(null)
  const sheet = sheetAt === props.path
  const setSheet = (open: boolean) => setSheetAt(open ? props.path : null)
  const { pinned } = group(props.boot.pages)
  const lit = activeHref(props.boot.pages, props.path)

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
  const tabs = pinned.filter((p) => ['floorPlan', 'seats', 'problems', 'incidents'].includes(p.id)).slice(0, 4)
  return (
    <>
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
                      {p.id === 'problems' && !!props.down && <span className="fb-nav-dot" aria-hidden="true" />}
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
  const byId = new Map(boot.pages.map((p) => [p.id, p]))
  const favourites = prefs.favourites.map((id) => byId.get(id)).filter((p): p is NavPage => !!p)
  const litSection = sections.find((s) => s.pages.some((p) => p.href === lit))?.id
  const [open, setOpen] = useState<string[]>(readOpen)
  // Folding the others: the one section opened by hand on this page (id null: closed by hand),
  // else the one with the page on screen.
  const [only, setOnly] = useState<{ id: SectionId | null; path: string } | null>(null)
  // Like the sheet: tied to the page and the fold it opened on, so either change closes it.
  const [flyoutAt, setFlyout] = useState<{ id: SectionId; top: number; path: string; rail: boolean } | null>(null)
  const flyout = flyoutAt && flyoutAt.path === props.path && flyoutAt.rail === rail ? flyoutAt : null

  const picked = only && only.path === props.path ? only : null   // a new page starts from its own section
  const isOpen = (id: SectionId) =>
    prefs.accordion ? (picked ? picked.id === id : id === litSection) : open.includes(id) || id === litSection
  const toggle = (id: SectionId) => {
    if (prefs.accordion) return setOnly({ id: isOpen(id) ? null : id, path: props.path })
    const next = isOpen(id) ? open.filter((x) => x !== id) : [...open, id]
    setOpen(next)
    saveOpen(next)
  }
  const isFav = (id: string) => prefs.favourites.includes(id)
  const toggleFav = (id: string) =>
    props.setPrefs({ ...prefs, favourites: isFav(id) ? prefs.favourites.filter((x) => x !== id) : [...prefs.favourites, id] })

  useEffect(() => {
    if (!flyout) return
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== 'Escape') return
      if (e.target instanceof Element && e.target.closest('.fb-nav-flyout, .fb-nav-section-head')) return
      setFlyout(null)
    }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('pointerdown', close)
    }
  }, [flyout])

  const row = (p: NavPage, star = !rail) => {
    const Icon = pageIcon(p.id)
    const label = t(`goto.pages.${p.id}`, { defaultValue: p.label })
    const badge = p.id === 'problems' && props.down ? props.down : null
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

  const flown = flyout && sections.find((s) => s.id === flyout.id)
  return (
    <>
      <div className="fb-nav-top">
        {props.renderLink({
          href: '/', className: 'fb-nav-brand', title: t('nav.home'),
          children: <Brand boot={boot} rail={rail} />,
        })}
      </div>

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
        {sections.map((s) => {
          const Icon = sectionIcon(s.id)
          const label = t(`nav.sections.${s.id}`)
          const expanded = rail ? flyout?.id === s.id : isOpen(s.id)
          return (
            <div key={s.id} className="fb-nav-section" data-lit={s.id === litSection || undefined}>
              <button
                type="button" className="fb-nav-row fb-nav-section-head" aria-expanded={expanded}
                title={rail ? label : undefined}
                onClick={(e) => {
                  if (!rail) return toggle(s.id)
                  const top = e.currentTarget.getBoundingClientRect().top
                  setFlyout(flyout?.id === s.id ? null : { id: s.id, top, path: props.path, rail })
                }}
              >
                <Icon size={18} className="fb-nav-icon" aria-hidden="true" />
                <span className="fb-nav-text">{label}</span>
                <IconChevronDown size={14} className="fb-nav-chevron" aria-hidden="true" />
              </button>
              {!rail && expanded && <ul className="fb-nav-list fb-nav-sub">{s.pages.map((p) => row(p))}</ul>}
            </div>
          )
        })}
      </div>

      {rail && flown && (
        <div className="fb-nav-flyout" style={{ top: Math.min(flyout.top, window.innerHeight - 48 - flown.pages.length * 36) }}>
          <div className="fb-nav-flyout-title">{t(`nav.sections.${flown.id}`)}</div>
          {/* Same rows as the open sidebar, so labels show even while it's folded. */}
          <PanelRows rows={flown.pages.map((p) => row(p, true))} />
        </div>
      )}

      <div className="fb-nav-foot">
        <Account {...props} />
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

function PanelRows({ rows }: { rows: ReactNode[] }) {
  // The flyout's rows always show their text: it is the open list of a folded sidebar.
  return <ul className="fb-nav-list fb-nav-flyout-list">{rows}</ul>
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

function Account(props: PanelProps) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const scheme = useScheme()
  const toggle = toggleScheme()
  const user = props.boot.user

  useEffect(() => {
    if (!open) return
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== 'Escape') return
      if (e.target instanceof Node && box.current?.contains(e.target) && !(e instanceof KeyboardEvent)) return
      setOpen(false)
    }
    document.addEventListener('keydown', close)
    document.addEventListener('pointerdown', close)
    return () => {
      document.removeEventListener('keydown', close)
      document.removeEventListener('pointerdown', close)
    }
  }, [open])

  const name = user ? user.name || user.username : t('nav.account')
  const run = (f: () => void) => () => { setOpen(false); f() }
  return (
    <div className="fb-nav-account" ref={box}>
      <button
        type="button" className="fb-nav-row fb-nav-me" aria-expanded={open} aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)} title={props.rail ? name : undefined}
        aria-label={user ? t('common.signedInAs', { username: user.username }) : t('nav.account')}
      >
        <span className="fb-nav-avatar" aria-hidden="true">{user ? initials(name) : <IconDots size={16} />}</span>
        <span className="fb-nav-text">{name}</span>
      </button>
      {open && (
        <div className="fb-nav-menu" role="menu" data-sheet={props.sheet || undefined}>
          {user && <div className="fb-nav-menu-label">{t('common.signedInAs', { username: user.username })}</div>}
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
          <button
            type="button" role="menuitemcheckbox" aria-checked={props.prefs.accordion} className="fb-nav-menu-item"
            onClick={run(() => props.setPrefs({ ...props.prefs, accordion: !props.prefs.accordion }))}
          >
            {t('nav.accordion')}
          </button>
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
