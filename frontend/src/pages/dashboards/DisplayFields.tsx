import { ActionIcon, Button, Group, NumberInput, Select, SegmentedControl, Stack, Switch, Text, TextInput } from '@mantine/core'
import { IconPlus, IconX } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import type { Tone, Widget } from '@/api/types'
import { type Mapping, SORTS, type Sort, type Threshold, displaysFor } from '@/widgets/kinds/display'
import type { Pane } from './model'

type TilePane = Extract<Pane, { kind: 'tile' }>
const TONES: Tone[] = ['ok', 'warn', 'err', '']
export const MAX_STEPS = 5
const num = (v: string | number) => (typeof v === 'number' ? v : undefined)

/** How a tile pane shows its numbers (issue #960): unit and decimals, colour steps, value
 *  mappings, and sort and top N. Each part shows only where the data has what it changes. */
export function DisplayFields({ pane, data, onChange }: { pane: TilePane; data: Widget; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  const can = displaysFor(data)
  const set = (patch: Partial<TilePane>) => onChange({ ...pane, ...patch })
  const tones = TONES.map((tone) => ({ value: tone || 'none', label: t(`dashboards.display.tone.${tone || 'none'}`) }))
  const steps = pane.thresholds ?? []
  const maps = pane.mappings ?? []
  const setSteps = (next: Threshold[]) => set({ thresholds: next.length ? next : undefined, threshold_mode: next.length ? pane.threshold_mode : undefined })
  const setMaps = (next: Mapping[]) => set({ mappings: next.length ? next : undefined })
  return (
    <Stack gap="sm">
      {can.numbers && (
        <Group grow align="flex-start">
          <TextInput label={t('dashboards.display.unit')} placeholder={t('dashboards.display.unitAuto')} maxLength={16}
            value={pane.unit ?? ''} onChange={(e) => set({ unit: e.currentTarget.value || undefined })} />
          <NumberInput label={t('dashboards.display.decimals')} placeholder={t('dashboards.display.auto')} min={0} max={4}
            value={pane.decimals ?? ''} onChange={(v) => set({ decimals: num(v) })} />
        </Group>
      )}
      {can.numbers && (
        <Switch label={t('dashboards.display.short')} checked={!!pane.short} onChange={(e) => set({ short: e.currentTarget.checked || undefined })} />
      )}
      {can.colours && (
        <div>
          <Text size="sm" fw={500}>{t('dashboards.display.thresholds')}</Text>
          <Text size="xs" c="dimmed" mb={6}>{t('dashboards.display.thresholdsHint')}</Text>
          <Stack gap={6}>
            {steps.map((st, i) => (
              <Group key={i} gap={6} wrap="nowrap">
                <NumberInput size="xs" aria-label={t('dashboards.display.from')} prefix="≥ " value={st.at}
                  onChange={(v) => setSteps(steps.map((x, k) => (k === i ? { ...x, at: num(v) ?? 0 } : x)))} />
                <Select size="xs" aria-label={t('dashboards.display.colour')} allowDeselect={false} data={tones} value={st.tone || 'none'}
                  onChange={(v) => setSteps(steps.map((x, k) => (k === i ? { ...x, tone: (v === 'none' ? '' : v) as Tone } : x)))} />
                <ActionIcon variant="subtle" color="gray" aria-label={t('dashboards.display.remove')} onClick={() => setSteps(steps.filter((_, k) => k !== i))}>
                  <IconX size={14} />
                </ActionIcon>
              </Group>
            ))}
            <Group gap={6}>
              <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} disabled={steps.length >= MAX_STEPS}
                onClick={() => setSteps([...steps, { at: steps.length ? steps[steps.length - 1].at + 10 : 80, tone: steps.length ? 'err' : 'warn' }])}>
                {t('dashboards.display.addStep')}
              </Button>
              {steps.length > 0 && (
                <SegmentedControl size="xs" value={pane.threshold_mode ?? 'value'} aria-label={t('dashboards.display.mode')}
                  data={[{ value: 'value', label: t('dashboards.display.byValue') }, { value: 'percent', label: t('dashboards.display.byPercent') }]}
                  onChange={(v) => set({ threshold_mode: v === 'percent' ? 'percent' : undefined })} />
              )}
            </Group>
          </Stack>
        </div>
      )}
      {can.colours && data.type !== 'series' && data.type !== 'sparkline' && (
        <div>
          <Text size="sm" fw={500}>{t('dashboards.display.mappings')}</Text>
          <Text size="xs" c="dimmed" mb={6}>{t('dashboards.display.mappingsHint')}</Text>
          <Stack gap={6}>
            {maps.map((m, i) => (
              <Group key={i} gap={6} wrap="nowrap">
                <NumberInput size="xs" w={70} aria-label={t('dashboards.display.from')} placeholder={t('dashboards.display.from')} value={m.from ?? ''}
                  onChange={(v) => setMaps(maps.map((x, k) => (k === i ? { ...x, from: num(v) } : x)))} />
                <NumberInput size="xs" w={70} aria-label={t('dashboards.display.to')} placeholder={t('dashboards.display.to')} value={m.to ?? ''}
                  onChange={(v) => setMaps(maps.map((x, k) => (k === i ? { ...x, to: num(v) } : x)))} />
                <TextInput size="xs" aria-label={t('dashboards.display.text')} placeholder={t('dashboards.display.text')} maxLength={40} value={m.text}
                  onChange={(e) => { const text = e.currentTarget.value; setMaps(maps.map((x, k) => (k === i ? { ...x, text } : x))) }} />
                <Select size="xs" w={110} aria-label={t('dashboards.display.colour')} allowDeselect={false} data={tones} value={m.tone || 'none'}
                  onChange={(v) => setMaps(maps.map((x, k) => (k === i ? { ...x, tone: v === 'none' ? undefined : (v as Tone) } : x)))} />
                <ActionIcon variant="subtle" color="gray" aria-label={t('dashboards.display.remove')} onClick={() => setMaps(maps.filter((_, k) => k !== i))}>
                  <IconX size={14} />
                </ActionIcon>
              </Group>
            ))}
            <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} disabled={maps.length >= MAX_STEPS * 2} w="fit-content"
              onClick={() => setMaps([...maps, { from: 0, to: 0, text: '', tone: 'err' }])}>
              {t('dashboards.display.addMapping')}
            </Button>
          </Stack>
        </div>
      )}
      {can.rows && (
        <Group grow align="flex-start">
          <Select label={t('dashboards.display.sort')} clearable placeholder={t('dashboards.display.sortData')} value={pane.sort ?? null}
            data={SORTS.map((s) => ({ value: s, label: t(`dashboards.display.sorts.${s}`) }))}
            onChange={(v) => set({ sort: (v as Sort) || undefined })} />
          <NumberInput label={t('dashboards.display.limit')} placeholder={t('dashboards.display.all')} min={1} max={100}
            value={pane.limit ?? ''} onChange={(v) => set({ limit: num(v) })} />
        </Group>
      )}
      {can.rows && can.numbers && (
        <Switch label={t('dashboards.display.hideZero')} checked={!!pane.hide_zero} onChange={(e) => set({ hide_zero: e.currentTarget.checked || undefined })} />
      )}
    </Stack>
  )
}
