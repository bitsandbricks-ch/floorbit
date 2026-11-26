import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'
import { LinkTabs } from '@bitsandbricks/ui'
import { activeHref, hubTabs, type NavPage } from '@/nav/sections'

/** The tabs of the sidebar row the page belongs to (issue #892): Helpdesk shows Problems,
 *  Incidents, My jobs, Handover and Status updates. Each tab is still its own page with its own
 *  address, so the shared LinkTabs draws them as links. */
export function HubTabs({ pages }: { pages: NavPage[] }) {
  const { t } = useTranslation()
  const path = useLocation().pathname
  const hub = hubTabs(pages, path)
  if (!hub) return null
  const lit = activeHref(hub.tabs, path)
  return (
    <div className="fb-hubtabs">
      <LinkTabs
        label={t(`goto.pages.${hub.hub}`)}
        active={hub.tabs.find((p) => p.href === lit)?.id ?? ''}
        tabs={hub.tabs.map((p) => ({ id: p.id, href: p.href, label: t(`goto.pages.${p.id}`, { defaultValue: p.label }) }))}
      />
    </div>
  )
}
