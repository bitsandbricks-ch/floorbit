import { IconBell } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useProblems } from '@/api/queries'
import { Notifications } from './Notifications'

/** The bell and its panel: in the top bar on a computer, in the header on a phone (#1396). */
export function NotificationsBell({ compact }: { compact?: boolean }) {
  const { t } = useTranslation()
  const problems = useProblems().data
  const [open, setOpen] = useState(false)
  // One number everywhere (issue #1413): the bell, the Helpdesk badge and the status line's first
  // number all count what is down. What needs a look is a dot here, and both are in the tooltip.
  const down = problems?.counts.down ?? 0
  const look = problems?.counts.look ?? problems?.counts.warn ?? 0
  const said = down ? t('nav.problemsSplit', { count: down, look }) : look ? t('bell.lookOnly', { count: look }) : null
  return (
    <>
      <button
        type="button" className={`fb-nav-icon-btn fb-topbar-bell${compact ? ' is-compact' : ''}`} onClick={() => setOpen(true)}
        aria-label={said ? `${t('nav.notifications')} (${said})` : t('nav.notifications')} title={said ?? t('nav.notifications')}
      >
        <IconBell size={compact ? 20 : 18} aria-hidden="true" />
        {down > 0 && <span className="fb-topbar-count is-down" aria-hidden="true">{down > 99 ? '99+' : down}</span>}
        {!down && look > 0 && <span className="fb-topbar-dot" aria-hidden="true" />}
      </button>
      {/* Only while open: the panel and its queries stay out of every page until the bell is pressed. */}
      {open && <Notifications opened onClose={() => setOpen(false)} />}
    </>
  )
}
