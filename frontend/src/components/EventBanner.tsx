import { IconCalendarEvent } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { pickEvent, useTenantEvents } from '@/api/tenantEvents'

/** On every crew page while this browser works on an event that isn't the live one
 *  (docs/tenancy.md), so nobody plans in the wrong event by mistake. Plain markup, no Mantine:
 *  the pages Flask draws load only the sidebar's code. ``floating`` for those pages. */
export function EventBanner({ floating = false }: { floating?: boolean }) {
  const { t } = useTranslation()
  const data = useTenantEvents()
  if (!data || data.current === data.live) return null
  const current = data.events.find((e) => e.id === data.current)
  const live = data.events.find((e) => e.id === data.live)
  if (!current) return null
  return (
    <div role="status" className={`fb-db-banner fb-event-banner${floating ? ' is-floating' : ''}`}>
      <IconCalendarEvent size={18} aria-hidden="true" />
      <div>
        <p className="fb-db-banner-title">
          {t('tenantEvents.banner.title', { name: current.name || t('tenantEvents.unnamed'), status: t(`tenantEvents.status.${current.status}`) })}
        </p>
        <p>{t('tenantEvents.banner.text', { live: live?.name || t('tenantEvents.unnamed') })}</p>
      </div>
      <button type="button" className="fb-event-banner-back" onClick={() => void pickEvent(null)}>
        {t('tenantEvents.banner.back')}
      </button>
    </div>
  )
}
