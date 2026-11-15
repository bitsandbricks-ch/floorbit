import { Button } from '@mantine/core'
import { IconBell, IconBellOff } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

/** Watch this seat (issue #178): static/js/notify.js shows a notification when its link changes.
 *  Kept with the other notification settings of this browser; watching turns notifications on. */
export function WatchSeat({ seat }: { seat: string }) {
  const { t } = useTranslation()
  const api = typeof window !== 'undefined' ? window.floorNotify : undefined
  const [watch, setWatch] = useState<string[]>(() => api?.settings().watch ?? [])
  const [denied, setDenied] = useState(false)
  if (!api || !api.supported()) return null
  const on = watch.includes(seat)
  const toggle = async () => {
    const next = on ? watch.filter((s) => s !== seat) : [...watch, seat].slice(-20)
    const prefs = await api.set(on ? { watch: next } : { watch: next, on: true })
    setWatch(prefs.watch ?? [])
    setDenied(!on && !prefs.on)
  }
  return (
    <Button variant={on ? 'filled' : 'default'} size="xs" onClick={() => void toggle()} aria-pressed={on}
      leftSection={on ? <IconBellOff size={14} /> : <IconBell size={14} />} title={denied ? t('plan.watch.denied') : undefined}>
      {on ? t('plan.watch.stop') : t('plan.watch.start')}
    </Button>
  )
}
