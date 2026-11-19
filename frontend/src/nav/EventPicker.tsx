import { IconCalendarEvent, IconSelector } from '@tabler/icons-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { pickEvent, useTenantEvents, type TenantEvent } from '@/api/tenantEvents'
import { useCloseOutside } from './closeOutside'
import type { NavPage } from './sections'

/** The event this browser works on, at the top of the sidebar: a click lists the tenant's events
 *  to switch to, and the event's own pages (schedule, changelog, replay, report: no sidebar rows of
 *  their own, issue #892). Plain markup like the rest of the sidebar. Shows nothing until the list answers. */
export function EventPicker({ rail, sheet, pages = [] }: { rail: boolean; sheet?: boolean; pages?: NavPage[] }) {
  const { t } = useTranslation()
  const data = useTenantEvents()
  const [open, setOpen] = useState(false)
  const [going, setGoing] = useState<string | null>(null)
  const box = useRef<HTMLDivElement>(null)
  useCloseOutside(open, setOpen, box)
  if (!Array.isArray(data?.events) || !data.events.length) return null
  const current = data.events.find((e) => e.id === data.current) ?? data.events[0]
  const name = (e: TenantEvent) => e.name || t('tenantEvents.unnamed')
  const go = (e: TenantEvent) => {
    if (e.id === data.current) return setOpen(false)
    setGoing(e.id)
    // The live one: follow it, so the next event made live is picked up by itself.
    void pickEvent(e.id === data.live ? null : e.id)
  }
  // Live first, then planning, then closed; newest first inside each.
  const order = { live: 0, planning: 1, closed: 2 }
  const events = [...data.events].sort((a, b) => order[a.status] - order[b.status] || (b.created_at ?? 0) - (a.created_at ?? 0))
  return (
    <div className="fb-nav-event" ref={box}>
      <button
        type="button" className="fb-nav-event-btn" aria-expanded={open} aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)} title={rail ? `${t('nav.event')}: ${name(current)}` : undefined}
        aria-label={rail ? `${t('nav.eventPick')}: ${name(current)}` : undefined}
      >
        {rail ? <IconCalendarEvent size={18} className="fb-nav-icon" aria-hidden="true" /> : <span className={`fb-bit is-${current.status}`} aria-hidden="true" />}
        <span className="fb-nav-event-text">
          <small>{t('nav.event')}</small>
          <b>{name(current)}</b>
        </span>
        <IconSelector size={14} className="fb-nav-event-mark" aria-hidden="true" />
      </button>
      {open && (
        <div className="fb-nav-menu fb-nav-event-menu" role="menu" data-sheet={sheet || undefined}>
          <div className="fb-nav-menu-label">{t('nav.eventPick')}</div>
          {events.map((e) => (
            <button
              key={e.id} type="button" role="menuitemradio" aria-checked={e.id === current.id}
              className="fb-nav-menu-item" disabled={!!going} onClick={() => go(e)}
            >
              <span className={`fb-bit is-${e.status}`} aria-hidden="true" />
              <span className="fb-nav-tenant-name">{name(e)}</span>
              <span className="fb-nav-tenant-how">{going === e.id ? t('nav.switching') : t(`tenantEvents.status.${e.status}`)}</span>
            </button>
          ))}
          <hr />
          {pages.filter((p) => p.id !== 'events').map((p) => (
            <a key={p.id} className="fb-nav-menu-item" href={p.href} role="menuitem">{t(`goto.pages.${p.id}`, { defaultValue: p.label })}</a>
          ))}
          <a className="fb-nav-menu-item" href="/events" role="menuitem">{t('nav.eventAll')}</a>
        </div>
      )}
    </div>
  )
}
