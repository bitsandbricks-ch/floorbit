import { type ReactNode, Suspense, useEffect } from 'react'
import { Skeleton, Stack } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { IconChevronLeft } from '@tabler/icons-react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { inApp } from '@/nav/sections'
import { usePageList } from '@/api/queries'
import { useLiveRefresh } from '@/api/liveRefresh'
import { useAppNav } from './AppNav'
import { DatabaseBanner } from './DatabaseBanner'
import { EventBanner } from './EventBanner'
import { HubTabs } from './HubTabs'
import { rememberPage } from './pages'
import { setPageTitle } from './pageTitle'
import { StatusLine } from './StatusLine'
import { TopBarCrumbs, TopBarEnd } from './TopBar'
import { AppShell as BnbAppShell, PageError, TitleLevel, useInPanel } from '@bitsandbricks/ui'

/** What shows in the page area while a page's code loads: the sidebar and top bar stay. */
export function PageSkeleton() {
  return (
    <div className="fb-page" aria-busy="true">
      <Stack gap="md">
        <Skeleton h={32} w="40%" radius="sm" />
        <Skeleton h={16} w="70%" radius="sm" />
        <Skeleton h={180} radius="lg" mt="sm" />
        <Skeleton h={120} radius="lg" />
      </Stack>
    </div>
  )
}

/** The crew pages' frame, drawn once for the whole app: the shared AppShell with Floorbit's
 *  sidebar, the top bar, the banners and the status line with the attribution. Pages change inside
 *  it, so moving between pages, or waiting for a page's code, never takes the sidebar away. */
export function AppShell({ children }: { children?: ReactNode }) {
  const { pathname, search } = useLocation()
  const params = new URLSearchParams(search)
  // The API's list only: the breadcrumbs link to its pages, and the list in the page (#fb-nav-data)
  // is text from the document.
  const pages = usePageList()
  const { shell, dialogs } = useAppNav()
  const phone = useMediaQuery('(max-width: 48em)', false, { getInitialValueInEffect: false })
  // The problem count and the crew notice follow the live events instead of asking every 30 s.
  useLiveRefresh()
  // A wall screen or a print sheet is the page alone: no sidebar, banners or footer on the TV or the paper.
  if (params.get('screen') === '1' || params.get('print') === '1') {
    return <Suspense fallback={<PageSkeleton />}>{children ?? <Outlet />}</Suspense>
  }
  const folded = shell.folded && !phone
  return (
    <>
      <BnbAppShell
        brand={shell.brand(folded)}
        navTop={shell.navTop}
        nav={shell.nav}
        navFooter={shell.navFooter}
        folded={shell.folded}
        onFoldedChange={shell.onFoldedChange}
        phoneNav={shell.phoneNav}
        title={<TopBarCrumbs pages={pages} />}
        topBarEnd={<TopBarEnd phone={phone} />}
        banner={<><HubTabs pages={pages} /><DatabaseBanner /><EventBanner /></>}
        status={<StatusLine bare />}
        dotGrid={false}
        actionsInTopBar
      >
        <PageError resetKey={pathname}>
          <Suspense fallback={<PageSkeleton />}>{children ?? <Outlet />}</Suspense>
        </PageError>
      </BnbAppShell>
      {dialogs}
    </>
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
    <div className={full ? 'fb-page fb-page-full' : 'fb-page'}>
      <h1 className="fb-sr-only">{title}</h1>
      {up && (
        <nav className="fb-up" aria-label={up.label}>
          {!inApp(up.href)
            ? <a href={up.href}><IconChevronLeft size={14} aria-hidden="true" />{up.label}</a>
            : <Link to={up.href}><IconChevronLeft size={14} aria-hidden="true" />{up.label}</Link>}
        </nav>
      )}
      {/* This h1 is the page's, so PageHead titles start at h2. */}
      <TitleLevel.Provider value={2}>{children}</TitleLevel.Provider>
    </div>
  )
}
