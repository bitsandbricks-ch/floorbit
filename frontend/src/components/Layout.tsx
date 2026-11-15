import type { ReactNode } from 'react'
import { IconChevronLeft, IconSearch } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { inApp } from '@/nav/sections'
import { readRail } from '@/nav/boot'
import { openGoTo } from '@/nav/goto'
import { AppNav } from './AppNav'
import { Attribution } from './Attribution'
import { CrewNoticeBanner } from './CrewNotice'
import { rememberPage } from './pages'

/** Every React page: the sidebar, the page title (a bar of its own on phones only; desktops show
 *  the page's PageHead), a way up for sub pages, and the attribution at the end.
 *  ``back`` names the parent page; the floor plan as parent needs no link, the sidebar has it.
 *  ``count`` goes in front of the tab title, so a background tab shows when something needs a look (issue #208).
 *  ``wide`` drops the reading width, for pages that are one big picture (the seats view). */
export function Layout({ title, back, count, wide, children }: {
  title: string; back?: { href: string; label: string }; count?: number; wide?: boolean; children: ReactNode
}) {
  const { t } = useTranslation()
  const path = useLocation().pathname
  useEffect(() => rememberPage(path), [path])
  useEffect(() => {
    document.title = `${count ? `(${count}) ` : ''}${title} · Floorbit`
  }, [title, count])
  const up = back && back.href !== '/' ? back : null
  return (
    <div className="fb-shell">
      <div className="fb-nav-slot" data-state={readRail() ? 'rail' : 'full'}>
        <AppNav />
      </div>
      <div className="fb-shell-main">
        {/* Phones: the brand and "Go to" on top, the sidebar's bar at the bottom. The page's own
            PageHead shows the title, so the heading here is for screen readers. */}
        <header className="fb-header">
          <Link to="/" reloadDocument className="fb-header-brand" aria-label={t('nav.homeBrand')}>
            <span className="fb-brand"><span className="fb-brand-lockup" aria-hidden="true" /></span>
          </Link>
          <h1 className="fb-sr-only">{title}</h1>
          <button type="button" className="fb-nav-icon-btn fb-header-search" onClick={openGoTo} aria-label={t('nav.search')}>
            <IconSearch size={20} aria-hidden="true" />
          </button>
        </header>
        <CrewNoticeBanner />
        <main className={wide ? 'fb-main fb-main-wide' : 'fb-main'}>
          {up && (
            <nav className="fb-up" aria-label={up.label}>
              {!inApp(up.href)
                ? <a href={up.href}><IconChevronLeft size={14} aria-hidden="true" />{up.label}</a>
                : <Link to={up.href}><IconChevronLeft size={14} aria-hidden="true" />{up.label}</Link>}
            </nav>
          )}
          {children}
        </main>
        <Attribution />
      </div>
    </div>
  )
}
