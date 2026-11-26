import { Button, NumberInput, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { PlanMark } from '@/api/types'
import { WALKWAY_DEFAULT, WALKWAY_MAX, WALKWAY_MIN } from '../lineMarks'

/** A walkway's own fields (#1564): how wide it is, in seats, and taking out its bends. Seat blocks
 *  snap to its edges, so the width is the space between the blocks on either side. */
export function WalkwayFields({ mark, onWidth, onStraighten }: {
  mark: PlanMark
  onWidth: (before: number, after: number) => void
  onStraighten: () => void
}) {
  const { t } = useTranslation()
  const width = mark.width ?? WALKWAY_DEFAULT
  return (
    <>
      <NumberInput key={width} label={t('walkways.width')} description={t('walkways.widthHint')} min={WALKWAY_MIN} max={WALKWAY_MAX} step={0.5}
        decimalScale={2} defaultValue={width} suffix={` ${t('walkways.seats', { count: width })}`} clampBehavior="strict"
        onBlur={(e) => {
          const v = Number(e.currentTarget.value.replace(/[^\d.]/g, ''))
          if (Number.isFinite(v) && v >= WALKWAY_MIN && v <= WALKWAY_MAX && v !== width) onWidth(width, v)
        }}
        onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} />
      <Text size="xs" c="dimmed">{t('walkways.help')}</Text>
      {!!mark.points?.length && (
        <Button size="xs" variant="default" onClick={onStraighten}>
          {t('plan.edit.wall.straighten', { count: mark.points.length })}
        </Button>
      )}
    </>
  )
}
