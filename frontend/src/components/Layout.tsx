import { type ReactNode, Suspense, useEffect } from 'react'
import { Skeleton, Stack } from '@mantine/core'
import { IconChevronLeft, IconSearch } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { inApp } from '@/nav/sections'
import { readRail } from '@/nav/boot'
import { openGoTo } from '@/nav/goto'
import { AppNav } from './AppNav'
import { Attribution } from './Attribution'
import { CrewNoticeBanner } from './CrewNotice'
import { rememberPage } from './pages'

/** What shows in the page area while a page's code loads: the sidebar and top bar stay. */
export function PageSkeleton() {
  return (
    <main className="fb-main" aria-busy="true">
      <Stack gap="md">
        <Skeleton h={32} w="40%" radius="sm" />
        <Skeleton h={16} w="70%" radius="sm" />
        <Skeleton h={180} radius="lg" mt="sm" />
        <Skeleton h={120} radius="lg" />
      </Stack>
    </main>
  )
}

/** The crew pages' frame, drawn once for the whole app: the sidebar, the phone top bar, the crew
 *  notice and the attribution. Pages change inside it, so moving between pages, or waiting for a
 *  page's code, never takes the sidebar away (it used to come and go with every page). */
export function AppShell({ children }: { children?: ReactNode }) {
  const { t } = useTranslation()
  return (
    <div className="fb-shell">
      <div className="fb-nav-slot" data-state={readRail() ? 'rail' : 'full'}>
        <AppNav />
      </div>
      <div className="fb-shell-main">
        {/* Phones: the brand and "Go to" on top, the sidebar's bar at the bottom. */}
        <header className="fb-header">
          <Link to="/" reloadDocument className="fb-header-brand" aria-label={t('nav.homeBrand')}>
            <span className="fb-brand"><span className="fb-brand-lockup" aria-hidden="true" /></span>
          </Link>
          <button type="button" className="fb-nav-icon-btn fb-header-search" onClick={openGoTo} aria-label={t('nav.search')}>
            <IconSearch size={20} aria-hidden="true" />
          </button>
        </header>
        <CrewNoticeBanner />
        <Suspense fallback={<PageSkeleton />}>{children ?? <Outlet />}</Suspense>
        <Attribution />
      </div>
    </div>
  )
}

/** One crew page inside the shell: the tab title, the page title for screen readers (desktops
 *  show the page's PageHead), and a way up for sub pages.
 *  ``back`` names the parent page; the floor plan as parent needs no link, the sidebar has it.
 *  ``count`` goes in front of the tab title, so a background tab shows when something needs a look (issue #208).
 *  ``wide`` drops the reading width, for pages that are one big picture (the seats view). */
export function Layout({ title, back, count, wide, children }: {
  title: string; back?: { href: string; label: string }; count?: number; wide?: boolean; children: ReactNode
}) {
  const path = useLocation().pathname
  useEffect(() => rememberPage(path), [path])
  useEffect(() => {
    document.title = `${count ? `(${count}) ` : ''}${title} · Floorbit`
  }, [title, count])
  const up = back && back.href !== '/' ? back : null
  return (
    <main className={wide ? 'fb-main fb-main-wide' : 'fb-main'}>
      <h1 className="fb-sr-only">{title}</h1>
      {up && (
        <nav className="fb-up" aria-label={up.label}>
          {!inApp(up.href)
            ? <a href={up.href}><IconChevronLeft size={14} aria-hidden="true" />{up.label}</a>
            : <Link to={up.href}><IconChevronLeft size={14} aria-hidden="true" />{up.label}</Link>}
        </nav>
      )}
      {children}
    </main>
  )
}
