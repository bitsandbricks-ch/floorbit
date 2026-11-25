import { NotificationsPanel } from '@bitsandbricks/ui'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMe, useProblems } from '@/api/queries'
import { ago } from '@/lib/time'
import { NotifyDetail } from './notifications/NotifyDetail'
import { GROUPS, notifyItems } from './notifications/list'
import { NotifySettings } from './NotifySettings'

/** The bell's panel (#1388), the shared NotificationsPanel: what needs a look right now, worst
 *  first, paged at 50, and the picked one's details beside the list. */
export function Notifications({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const me = useMe().data
  const q = useProblems()
  const [settings, setSettings] = useState(false)
  const items = useMemo(() => notifyItems(q.data), [q.data])
  const filters = GROUPS.map((g) => ({ value: g, label: t(`notifications.filter.${g}`) }))
  return (
    <>
      <NotificationsPanel
        opened={opened} onClose={onClose} items={items} loading={q.isPending} filters={filters}
        eyebrow={q.data ? t('notifications.eyebrow', { ago: ago(q.data.checked_at), count: items.length }) : undefined}
        renderDetail={(item) => <NotifyDetail id={item.id} />}
        allHref="/problems" onSettings={me?.user ? () => setSettings(true) : undefined}
        storageKey="floorbit:notifications-width"
      />
      {settings && <NotifySettings opened onClose={() => setSettings(false)} />}
    </>
  )
}
