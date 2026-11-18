import { Button, Group, NumberInput, Slider, Stack, Text } from '@mantine/core'
import { IconArrowsMove, IconMaximize, IconRulerMeasure } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

/** The hall's background in the editor panel, with nothing selected: how see-through it is, moving
 *  and scaling it on the plan, putting it back on the whole plan, and where the scale comes from. */
export function BackgroundFields({ opacity, placing, seatM, onOpacity, onPlacing, onFit }: {
  opacity: number; placing: boolean; seatM: number | null | undefined
  onOpacity: (v: number) => void; onPlacing: (on: boolean) => void; onFit: () => void
}) {
  const { t } = useTranslation()
  const [shown, setShown] = useState(Math.round(opacity * 100))
  return (
    <Stack gap="xs" role="group" aria-label={t('plan.edit.background.title')}>
      <Text size="xs" fw={700} tt="uppercase" c="dimmed">{t('plan.edit.background.title')}</Text>
      <div>
        <Text size="sm" fw={500} mb={4}>{t('plan.edit.background.opacity')}</Text>
        <Slider min={5} max={100} step={5} value={shown} onChange={setShown} onChangeEnd={(v) => onOpacity(v / 100)}
          label={(v) => `${v} %`} thumbLabel={t('plan.edit.background.opacity')} />
      </div>
      <Group gap="xs">
        <Button size="xs" variant={placing ? 'filled' : 'default'} leftSection={<IconArrowsMove size={14} />} aria-pressed={placing}
          onClick={() => onPlacing(!placing)}>{t(placing ? 'plan.edit.background.donePlacing' : 'plan.edit.background.place')}</Button>
        <Button size="xs" variant="default" leftSection={<IconMaximize size={14} />} onClick={onFit}>{t('plan.edit.background.fit')}</Button>
      </Group>
      <Text size="xs" c="dimmed">
        <IconRulerMeasure size={12} style={{ verticalAlign: -1 }} />{' '}
        {seatM ? t('plan.edit.background.scaleKnown', { m: seatM }) : t('plan.edit.background.scaleHelp')}
      </Text>
    </Stack>
  )
}

/** Under the Measure tool, once a line is drawn: give its real length to set the hall's scale from
 *  it, or (with a scale) to fit the background to the seats. */
export function CalibrateFields({ seats, seatM, hasBackground, onScale, onFit }: {
  seats: number; seatM: number | null | undefined; hasBackground: boolean
  onScale: (metres: number) => void; onFit: (metres: number) => void
}) {
  const { t } = useTranslation()
  const [metres, setMetres] = useState<number | ''>('')
  const ok = typeof metres === 'number' && metres > 0
  return (
    <Stack gap="xs" role="group" aria-label={t('plan.edit.calibrate.title')}>
      <Text size="xs" fw={700} tt="uppercase" c="dimmed">{t('plan.edit.calibrate.title')}</Text>
      <Text size="sm">{t('plan.edit.calibrate.measured', { seats: Math.round(seats * 10) / 10 })}</Text>
      <NumberInput label={t('plan.edit.calibrate.metres')} min={0.01} max={10000} decimalScale={2} suffix=" m" value={metres}
        onChange={(v) => setMetres(typeof v === 'number' ? v : '')} />
      <Button size="xs" variant="default" disabled={!ok} onClick={() => ok && onScale(metres)}>{t('plan.edit.calibrate.setScale')}</Button>
      {hasBackground && (
        <Button size="xs" variant="default" disabled={!ok || !seatM} onClick={() => ok && onFit(metres)}>{t('plan.edit.calibrate.fit')}</Button>
      )}
      <Text size="xs" c="dimmed">{t(hasBackground ? 'plan.edit.calibrate.helpBackground' : 'plan.edit.calibrate.help')}</Text>
    </Stack>
  )
}
