import { Text } from '@mantine/core'
import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useSize } from '../plan/useSize'
import type { ListedSeat } from './problemSeats'

// One line of the list in pixels (PlanPane.css), to know how many fit.
const LINE = 22

/** Beside a wide plan pane: which seats need attention, as many as fit, then "+N more". */
export function ProblemList({ seats }: { seats: ListedSeat[] }) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDivElement>(null)
  const { h } = useSize(ref)
  // The heading takes a line; keep one for "+N more" when they don't all fit.
  const room = Math.max(1, Math.floor(h / LINE) - 1)
  const shown = seats.length > room ? seats.slice(0, room - 1) : seats
  return (
    <div ref={ref} className="fb-plan-list" role="list" aria-label={t('hallPlan.attention')}>
      <Text className="fb-plan-list-head">{t('hallPlan.attention')}</Text>
      {shown.map((s) => (
        <div key={s.seat} role="listitem" className="fb-plan-list-row">
          <span>{s.seat}</span>
          <span className={`st st-${s.state}`}>{s.state === 'offline' ? t('plan.state.offline') : t('hallPlan.problems', { count: s.problems })}</span>
        </div>
      ))}
      {shown.length < seats.length && <Text className="fb-plan-list-more">{t('hallPlan.more', { count: seats.length - shown.length })}</Text>}
    </div>
  )
}
