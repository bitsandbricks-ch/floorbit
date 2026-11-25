import { ActionIcon, Group, NumberInput, Text } from '@mantine/core'
import { IconX } from '@tabler/icons-react'
import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { type Gap, GAP_MAX, GAP_MIN, cleanGaps } from './gaps'
import './RowSeatStrip.css'

/** A row's seats in a line with its gaps (#1547): click between two seats to add a gap there, click
 *  a gap to size or remove it. Seat numbers carry on across a gap. */
export function RowSeatStrip({ seats, gaps, onSave }: { seats: number; gaps: Gap[]; onSave: (gaps: Gap[]) => void }) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState<number | null>(null)
  const at = new Map(gaps.map((g) => [g.after, g.size]))
  const sel = picked != null && at.has(picked) ? picked : null
  const save = (next: Gap[]) => onSave(cleanGaps(next, seats))
  return (
    <div>
      <Text size="sm" fw={500} mb={4}>{t('rowSpacers.stripTitle')}</Text>
      <div className="fb-seat-strip" role="group" aria-label={t('rowSpacers.stripTitle')}>
        {Array.from({ length: seats }, (_, i) => i + 1).map((n) => (
          <Fragment key={n}>
            <span className="fb-seat-strip-seat" aria-hidden="true" />
            {n < seats && (at.has(n) ? (
              <button type="button" className={sel === n ? 'fb-seat-strip-gap on' : 'fb-seat-strip-gap'} style={{ width: Math.min(40, 6 + at.get(n)! * 8) }}
                aria-pressed={sel === n} aria-label={t('rowSpacers.gapAfter', { seat: n, count: at.get(n) })} onClick={() => setPicked(sel === n ? null : n)} />
            ) : (
              <button type="button" className="fb-seat-strip-slot" aria-label={t('rowSpacers.addAfter', { seat: n })}
                onClick={() => { save([...gaps, { after: n, size: 1 }]); setPicked(n) }} />
            ))}
          </Fragment>
        ))}
      </div>
      {sel != null ? (
        <Group gap="xs" wrap="nowrap" mt={6}>
          <Text size="xs" c="dimmed" style={{ flex: 1 }}>{t('rowSpacers.gapAfterShort', { seat: sel })}</Text>
          <NumberInput key={`${sel}-${at.get(sel)}`} size="xs" w={96} min={GAP_MIN} max={GAP_MAX} step={0.5} decimalScale={2} defaultValue={at.get(sel)}
            aria-label={t('rowSpacers.gapSize', { seat: sel })} suffix={` ${t('rowSpacers.unit', { count: at.get(sel) })}`}
            onBlur={(e) => {
              const v = Number(e.currentTarget.value.replace(/[^\d.]/g, ''))
              if (Number.isFinite(v) && v > 0 && v !== at.get(sel)) save(gaps.map((g) => (g.after === sel ? { ...g, size: v } : g)))
            }} />
          <ActionIcon size="sm" variant="subtle" color="gray" aria-label={t('rowSpacers.removeGap', { seat: sel })}
            onClick={() => { save(gaps.filter((g) => g.after !== sel)); setPicked(null) }}><IconX size={14} /></ActionIcon>
        </Group>
      ) : <Text size="xs" c="dimmed" mt={4}>{t('rowSpacers.stripHint')}</Text>}
    </div>
  )
}
