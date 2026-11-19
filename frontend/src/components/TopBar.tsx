import { IconBell, IconChevronRight, IconSearch } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'
import { useProblems } from '@/api/queries'
import { openGoTo } from '@/nav/goto'
import { crumbsFor } from '@/nav/crumbs'
import { inApp, isPluginPage, type NavPage } from '@/nav/sections'
import { Notifications } from './Notifications'
import { usePageTitle } from './pageTitle'

const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

/** The bar above every crew page on a desktop: where you are, "Go to" and the notifications. */
export function TopBar({ pages }: { pages: NavPage[] }) {
  const { t } = useTranslation()
  const path = useLocation().pathname
  const title = usePageTitle()
  const problems = useProblems().data
  const [open, setOpen] = useState(false)
  const { section, page } = crumbsFor(pages, path)
  const label = page ? (isPluginPage(page.id) ? page.label : t(`goto.pages.${page.id}`, { defaultValue: page.label })) : null
  // A sub page (one agent, one device): its own title after the page it belongs to.
  const sub = page && page.href !== path && title && title !== label ? title : null
  const count = (problems?.counts.down ?? 0) + (problems?.counts.warn ?? 0)
  return (
    <header className="fb-topbar">
      <nav className="fb-crumbs" aria-label={t('nav.breadcrumbs')}>
        {section && <span className="fb-crumb-section">{t(`nav.sections.${section}`)}</span>}
        {section && (label || title) && <IconChevronRight size={13} className="fb-crumb-sep" aria-hidden="true" />}
        {sub && page ? (
          <>
            {inApp(page.href) ? <Link to={page.href}>{label}</Link> : <a href={page.href}>{label}</a>}
            <IconChevronRight size={13} className="fb-crumb-sep" aria-hidden="true" />
            <b aria-current="page">{sub}</b>
          </>
        ) : (
          <b aria-current="page">{label ?? title}</b>
        )}
      </nav>
      <button type="button" className="fb-topbar-search" onClick={openGoTo} aria-keyshortcuts="Control+K Meta+K">
        <IconSearch size={15} aria-hidden="true" />
        <span>{t('nav.search')}</span>
        <kbd className="fb-nav-kbd">{mac ? '⌘K' : 'Ctrl K'}</kbd>
      </button>
      <button
        type="button" className="fb-nav-icon-btn fb-topbar-bell" onClick={() => setOpen(true)}
        aria-label={count ? `${t('nav.notifications')} (${count})` : t('nav.notifications')} title={t('nav.notifications')}
      >
        <IconBell size={18} aria-hidden="true" />
        {count > 0 && <span className={problems?.counts.down ? 'fb-topbar-count is-down' : 'fb-topbar-count'} aria-hidden="true">{count}</span>}
      </button>
      <Notifications opened={open} onClose={() => setOpen(false)} />
    </header>
  )
}
