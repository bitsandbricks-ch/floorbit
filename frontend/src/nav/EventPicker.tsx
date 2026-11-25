import { IconCalendarEvent, IconSelector } from '@tabler/icons-react'
import { useState } from 'react'
import { Menu, UnstyledButton } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { pickEvent, useTenantEvents, type TenantEvent } from '@/api/tenantEvents'

/** The event this browser works on, at the top of the sidebar: a click lists the tenant's events
 *  to switch to. The event's pages have their own sidebar row, Events (issue #1201). A menu that
 *  opens beside the folded sidebar. Shows nothing until the list answers. */
export function EventPicker({ rail }: { rail: boolean }) {
  const { t } = useTranslation()
  const data = useTenantEvents()
  const [going, setGoing] = useState<string | null>(null)
  if (!Array.isArray(data?.events) || !data.events.length) return null
  const current = data.events.find((e) => e.id === data.current) ?? data.events[0]
  const name = (e: TenantEvent) => e.name || t('tenantEvents.unnamed')
  const go = (e: TenantEvent) => {
    if (e.id === data.current) return
    setGoing(e.id)
    // The live one: follow it, so the next event made live is picked up by itself.
    void pickEvent(e.id === data.live ? null : e.id)
  }
  // Live first, then planning, then closed; newest first inside each.
  const order = { live: 0, planning: 1, closed: 2 }
  const events = [...data.events].sort((a, b) => order[a.status] - order[b.status] || (b.created_at ?? 0) - (a.created_at ?? 0))
  return (
    <Menu position={rail ? 'right-start' : 'bottom-start'} width={rail ? 240 : 'target'} withinPortal>
      <Menu.Target>
        <UnstyledButton
          className="fb-nav-event-btn" data-rail={rail || undefined}
          title={rail ? `${t('nav.event')}: ${name(current)}` : undefined}
          aria-label={rail ? `${t('nav.eventPick')}: ${name(current)}` : undefined}
        >
          {rail ? <IconCalendarEvent size={18} className="fb-nav-icon" aria-hidden="true" /> : <span className={`fb-bit is-${current.status}`} aria-hidden="true" />}
          {!rail && (
            <span className="fb-nav-event-text">
              <small>{t('nav.event')}</small>
              <b>{name(current)}</b>
            </span>
          )}
          {!rail && <IconSelector size={14} className="fb-nav-event-mark" aria-hidden="true" />}
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{t('nav.eventPick')}</Menu.Label>
        {events.map((e) => (
          <Menu.Item
            key={e.id} aria-current={e.id === current.id ? 'true' : undefined} className="fb-nav-menu-item"
            disabled={!!going} closeMenuOnClick={false} onClick={() => go(e)}
            leftSection={<span className={`fb-bit is-${e.status}`} aria-hidden="true" />}
            rightSection={<span className="fb-nav-tenant-how">{going === e.id ? t('nav.switching') : t(`tenantEvents.status.${e.status}`)}</span>}
          >
            {name(e)}
          </Menu.Item>
        ))}
        <Menu.Divider />
        <Menu.Item component="a" href="/events">{t('nav.eventAll')}</Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}
