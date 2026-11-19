import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'
import { activeHref, hubTabs, inApp, type NavPage } from '@/nav/sections'

/** The tabs of the sidebar row the page belongs to (issue #892): Helpdesk shows Problems,
 *  Incidents, My jobs, Handover and Status updates. Each tab is still its own page with its own
 *  address; these are links, so a tab can be opened in a new browser tab too. */
export function HubTabs({ pages }: { pages: NavPage[] }) {
  const { t } = useTranslation()
  const path = useLocation().pathname
  const hub = hubTabs(pages, path)
  if (!hub) return null
  const lit = activeHref(hub.tabs, path)
  return (
    <nav className="fb-hubtabs" aria-label={t(`goto.pages.${hub.hub}`)}>
      {hub.tabs.map((p) => {
        const props = { className: 'fb-hubtab', 'aria-current': p.href === lit ? 'page' as const : undefined }
        const label = t(`goto.pages.${p.id}`, { defaultValue: p.label })
        return inApp(p.href)
          ? <Link key={p.id} to={p.href} {...props}>{label}</Link>
          : <a key={p.id} href={p.href} {...props}>{label}</a>
      })}
    </nav>
  )
}
