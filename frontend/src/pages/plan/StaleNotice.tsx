import { Badge, Tooltip } from '@mantine/core'
import { IconPlugConnectedX } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { clock } from '@/lib/time'
import { staleFor } from './stale'

/** A loud "not updated since" when the plan stops getting answers, so a wall screen never shows
 *  old seat states as if they were live. Nothing while all is well. */
export function StaleNotice({ updatedAt, failing }: { updatedAt: number; failing: boolean }) {
  const { t, i18n } = useTranslation()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 10_000)
    return () => window.clearInterval(timer)
  }, [])
  const age = staleFor(updatedAt, Math.max(now, updatedAt), failing)
  if (!age) return null
  const time = clock(new Date(updatedAt), i18n.language)
  return (
    <Tooltip label={t('plan.stale.help')} multiline w={260}>
      <Badge color="down" variant="filled" size="lg" leftSection={<IconPlugConnectedX size={14} />} role="status" className="fb-plan-stale">
        {t('plan.stale.since', { time })}
      </Badge>
    </Tooltip>
  )
}
