import { IconSearch } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'
import { Breadcrumbs, type Crumb } from '@bitsandbricks/ui'
import { openGoTo } from '@/nav/goto'
import { crumbsFor } from '@/nav/crumbs'
import { isPluginPage, type NavPage } from '@/nav/sections'
import { CrewNoticeBadge } from './CrewNotice'
import { NotificationsBell } from './NotificationsBell'
import { usePageTitle } from './pageTitle'

// The page list comes in the page itself (#fb-nav-data): link only to a path on this server.
const isLocalPath = (href: string) => /^\/(?!\/)/.test(href)

const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

/** Where you are, in the shared top bar: section, page, and the sub page's own title. */
export function TopBarCrumbs({ pages }: { pages: NavPage[] }) {
  const { t } = useTranslation()
  const path = useLocation().pathname
  const title = usePageTitle()
  const crumbs = crumbsFor(pages, path)
  const page = crumbs.page
  const label = page ? (isPluginPage(page.id) ? page.label : t(`goto.pages.${page.id}`, { defaultValue: page.label })) : null
  // "Inventory > Inventory" says nothing twice: a section named like its page is left out.
  const section = crumbs.section && t(`nav.sections.${crumbs.section}`) !== label ? crumbs.section : null
  // The page's own title after its row: a sub page (one agent, one device), or a tab of a row
  // (Helpdesk > Problems). The breadcrumb is the page's only title on a computer (issue #932).
  const sub = page && title && title !== label ? title : null
  const items: Crumb[] = []
  if (section) items.push({ label: t(`nav.sections.${section}`) })
  if (sub && page) items.push({ label, href: isLocalPath(page.href) ? page.href : undefined }, { label: sub })
  else if (label ?? title) items.push({ label: label ?? title })
  return <Breadcrumbs items={items} />
}

/** The top bar's right end: the crew notice, "Go to" and the notifications. Phones get the small kinds. */
export function TopBarEnd({ phone }: { phone: boolean }) {
  const { t } = useTranslation()
  return (
    <>
      <CrewNoticeBadge compact={phone} />
      {phone ? (
        <button type="button" className="fb-nav-icon-btn" onClick={openGoTo} aria-label={t('nav.search')}>
          <IconSearch size={20} aria-hidden="true" />
        </button>
      ) : (
        <button type="button" className="fb-topbar-search" onClick={openGoTo} aria-keyshortcuts="Control+K Meta+K"
          aria-label={t('nav.search')} title={t('nav.search')}>
          <IconSearch size={15} aria-hidden="true" />
          <kbd className="fb-nav-kbd">{mac ? '⌘K' : 'Ctrl K'}</kbd>
        </button>
      )}
      <NotificationsBell compact={phone} />
    </>
  )
}
