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
  const count = problems?.counts.total ?? (problems?.counts.down ?? 0) + (problems?.counts.warn ?? 0)
  return (
    <>
      <button
        type="button" className={`fb-nav-icon-btn fb-topbar-bell${compact ? ' is-compact' : ''}`} onClick={() => setOpen(true)}
        aria-label={count ? `${t('nav.notifications')} (${count})` : t('nav.notifications')} title={t('nav.notifications')}
      >
        <IconBell size={compact ? 20 : 18} aria-hidden="true" />
        {count > 0 && <span className={problems?.counts.down ? 'fb-topbar-count is-down' : 'fb-topbar-count'} aria-hidden="true">{count}</span>}
      </button>
      {/* Only while open: the panel and its queries stay out of every page until the bell is pressed. */}
      {open && <Notifications opened onClose={() => setOpen(false)} />}
    </>
  )
}
