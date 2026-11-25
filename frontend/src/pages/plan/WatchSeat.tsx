import { Button } from '@mantine/core'
import { IconBell, IconBellOff } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { crewNotify, setWatchedSeats, watchedSeats } from '@/notify/crewNotify'

/** Watch this seat (issue #178): a notification when its link changes (notify/CrewNotify.tsx).
 *  Kept in this browser; watching turns notifications on. */
export function WatchSeat({ seat }: { seat: string }) {
  const { t } = useTranslation()
  const [watch, setWatch] = useState<string[]>(watchedSeats)
  const [denied, setDenied] = useState(false)
  if (!crewNotify.supported()) return null
  const on = watch.includes(seat)
  const toggle = async () => {
    const next = on ? watch.filter((s) => s !== seat) : [...watch, seat]
    setWatchedSeats(next)
    setWatch(watchedSeats())
    if (!on) setDenied(!(await crewNotify.set({ on: true })).on)
  }
  return (
    <Button variant={on ? 'filled' : 'default'} size="xs" onClick={() => void toggle()} aria-pressed={on}
      leftSection={on ? <IconBellOff size={14} /> : <IconBell size={14} />} title={denied ? t('plan.watch.denied') : undefined}>
      {on ? t('plan.watch.stop') : t('plan.watch.start')}
    </Button>
  )
}
