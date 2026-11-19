import { type ReactNode, Suspense, useEffect } from 'react'
import { Skeleton, Stack } from '@mantine/core'
import { IconChevronLeft, IconSearch } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { inApp } from '@/nav/sections'
import { readRail } from '@/nav/boot'
import { usePageList } from '@/api/queries'
import { openGoTo } from '@/nav/goto'
import { AppNav } from './AppNav'
import { CrewNoticeBanner } from './CrewNotice'
import { DatabaseBanner } from './DatabaseBanner'
import { EventBanner } from './EventBanner'
import { HubTabs } from './HubTabs'
import { PageError } from './PageError'
import { rememberPage } from './pages'
import { useInPanel } from './panel'
import { setPageTitle } from './pageTitle'
import { StatusLine } from './StatusLine'
import { TopBar } from './TopBar'

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

/** The crew pages' frame, drawn once for the whole app: the sidebar, the top bar (the phone's
 *  own on phones), the crew notice and the status line with the attribution. Pages change inside it, so moving between pages, or waiting for a
 *  page's code, never takes the sidebar away (it used to come and go with every page). */
export function AppShell({ children }: { children?: ReactNode }) {
  const { t } = useTranslation()
  const { pathname, search } = useLocation()
  const params = new URLSearchParams(search)
  // The API's list only: the breadcrumbs link to its pages, and the list in the page (#fb-nav-data)
  // is text from the document.
  const pages = usePageList()
  // A wall screen or a print sheet is the page alone: no sidebar, banners or footer on the TV or the paper.
  if (params.get('screen') === '1' || params.get('print') === '1') {
    return <Suspense fallback={<PageSkeleton />}>{children ?? <Outlet />}</Suspense>
  }
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
        {/* Desktops: where you are, "Go to" and the notifications. */}
        <TopBar pages={pages} />
        <HubTabs pages={pages} />
        <DatabaseBanner />
        <EventBanner />
        <CrewNoticeBanner />
        <PageError resetKey={pathname}>
          <Suspense fallback={<PageSkeleton />}>{children ?? <Outlet />}</Suspense>
        </PageError>
        <StatusLine />
      </div>
    </div>
  )
}

/** One crew page inside the shell: the tab title, the page title for screen readers (desktops
 *  show the page's PageHead), and a way up for sub pages.
 *  ``back`` names the parent page; the floor plan as parent needs no link, the sidebar has it.
 *  ``count`` goes in front of the tab title, so a background tab shows when something needs a look (issue #208).
 *  ``full`` makes the page a workspace like a map editor: no padding and no page scroll, the page
 *  fills every pixel next to the sidebar and sizes its own parts (the floor plan). */
export function Layout({ title, back, count, full, children }: {
  title: string; back?: { href: string; label: string }; count?: number; full?: boolean; children: ReactNode
}) {
  const path = useLocation().pathname
  const inPanel = useInPanel()
  useEffect(() => { if (!inPanel) rememberPage(path) }, [path, inPanel])
  useEffect(() => {
    if (inPanel) return
    document.title = `${count ? `(${count}) ` : ''}${title} · Floorbit`
    setPageTitle(title)
  }, [title, count, inPanel])
  if (inPanel) return <>{children}</>
  const up = back && back.href !== '/' ? back : null
  return (
    <main className={full ? 'fb-main fb-main-full' : 'fb-main'}>
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
