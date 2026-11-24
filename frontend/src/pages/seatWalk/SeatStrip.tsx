import { Group, Stack, Text, Tooltip, UnstyledButton } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { WalkSeat } from '@/api/seatWalk'
import './SeatStrip.css'

export type SeatState = 'mapped' | 'open' | 'failed' | 'marked'

function seatState(s: WalkSeat): SeatState {
  if (s.port) return 'mapped'
  if (s.mark) return 'marked'
  if (s.failed) return 'failed'
  return 'open'
}

/** The walk's seats in walking order (issue #1357): where it got to at a glance, and any seat can
 *  be picked to check it now instead of walking there in order. */
export function SeatStrip({ seats, at, onPick }: { seats: WalkSeat[]; at: number; onPick: (n: number) => void }) {
  const { t } = useTranslation()
  return (
    <Stack gap={6}>
      <Group justify="space-between" gap="xs">
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{t('seatWalkRows.strip')}</Text>
        <Text size="xs" c="dimmed">{t('seatWalkRows.stripHint')}</Text>
      </Group>
      <div className="walk-strip-seats" role="list" aria-label={t('seatWalkRows.strip')}>
        {seats.map((s, i) => {
          const state = seatState(s)
          const label = i === at ? t('seatWalkRows.seatState.current', { seat: s.seat })
            : t(`seatWalkRows.seatState.${state}`, { seat: s.seat, mark: s.mark ? t(`seatWalkRows.markShort.${s.mark.mark}`) : '' })
          const button = (
            <UnstyledButton key={s.seat} role="listitem" className="walk-strip-seat" data-state={state}
              data-current={i === at || undefined} aria-label={label} aria-current={i === at ? 'step' : undefined}
              onClick={() => onPick(i)}>
              {s.seat}
            </UnstyledButton>
          )
          return s.mark?.note ? <Tooltip key={s.seat} label={s.mark.note}>{button}</Tooltip> : button
        })}
      </div>
    </Stack>
  )
}
