import { Button, Tooltip } from '@mantine/core'
import { IconArrowRight } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'

type Hall = { id: string; name: string; problems?: number }

/** Seats with problems in the other halls (issue #874): short enough for a laptop's top bar, and
 *  one click opens the hall with the most of them. The full sentence is its tooltip and name. */
export function Elsewhere({ halls, current, onHall }: { halls: Hall[]; current: string; onHall: (id: string) => void }) {
  const { t } = useTranslation()
  const others = halls.filter((h) => h.id !== current && (h.problems ?? 0) > 0)
  const count = others.reduce((n, h) => n + (h.problems ?? 0), 0)
  if (!count) return null
  const worst = others.reduce((a, b) => ((b.problems ?? 0) > (a.problems ?? 0) ? b : a))
  const full = t('plan.elsewhere', { count })
  return (
    <Tooltip label={full}>
      <Button size="compact-sm" variant="light" color="down" className="fb-ws-elsewhere" aria-label={full}
        rightSection={<IconArrowRight size={14} aria-hidden="true" />} onClick={() => onHall(worst.id)}>
        {others.length === 1 ? t('planElsewhere.inHall', { count, hall: worst.name }) : t('planElsewhere.inHalls', { count })}
      </Button>
    </Tooltip>
  )
}
