import { ActionIcon, Button, Checkbox, Group, NumberInput, Select, Stack, Switch, Text, TextInput } from '@mantine/core'
import { IconPlus, IconX } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import { MAX_OVERRIDES, type Override, SERIES_COLOURS, type SeriesColour, seriesColour, seriesLabels } from '@/widgets/kinds/display'
import type { Pane } from './model'

type TilePane = Extract<Pane, { kind: 'tile' }>
const num = (v: string | number) => (typeof v === 'number' ? v : undefined)

/** A graph's value axis (#960): fixed ends and a log scale. */
export function AxisFields({ pane, onChange }: { pane: TilePane; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  const set = (patch: Partial<TilePane>) => onChange({ ...pane, ...patch })
  return (
    <div>
      <Text size="sm" fw={500}>{t('dashboards.display.axis')}</Text>
      <Text size="xs" c="dimmed" mb={6}>{t('dashboards.display.axisHint')}</Text>
      <Group grow align="flex-start">
        <NumberInput size="xs" label={t('dashboards.display.yMin')} placeholder={t('dashboards.display.auto')} value={pane.y_min ?? ''}
          onChange={(v) => set({ y_min: num(v) })} />
        <NumberInput size="xs" label={t('dashboards.display.yMax')} placeholder={t('dashboards.display.auto')} value={pane.y_max ?? ''}
          onChange={(v) => set({ y_max: num(v) })} />
      </Group>
      <Switch mt="xs" label={t('dashboards.display.yLog')} checked={!!pane.y_log} onChange={(e) => set({ y_log: e.currentTarget.checked || undefined })} />
    </div>
  )
}

/** Per series (or row), found by its label: another name, a colour, or hidden (#960). */
export function OverrideFields({ pane, data, onChange }: { pane: TilePane; data: Widget; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  const labels = seriesLabels(data)
  const rows = pane.overrides ?? []
  const setRows = (next: Override[]) => onChange({ ...pane, overrides: next.length ? next : undefined })
  const edit = (i: number, patch: Partial<Override>) => setRows(rows.map((x, k) => (k === i ? { ...x, ...patch } : x)))
  // A saved setting whose series is gone still shows, so it can be removed.
  const options = (match: string) => [...new Set([...labels, ...(match ? [match] : [])])]
  const colours = [{ value: 'auto', label: t('dashboards.display.colourAuto') },
    ...SERIES_COLOURS.map((c) => ({ value: c, label: t(`dashboards.display.colours.${c}`) }))]
  const free = labels.find((l) => !rows.some((r) => r.match === l))
  if (!labels.length && !rows.length) return null
  return (
    <div>
      <Text size="sm" fw={500}>{t(data.type === 'series' ? 'dashboards.display.series' : 'dashboards.display.rowsLook')}</Text>
      <Text size="xs" c="dimmed" mb={6}>{t('dashboards.display.seriesHint')}</Text>
      <Stack gap={6}>
        {rows.map((o, i) => (
          // Two lines, so the names fit the narrow side panel.
          <Stack key={i} gap={4} className="fb-series-row">
            <Group gap={6} wrap="nowrap">
              <Select size="xs" style={{ flex: 1 }} searchable allowDeselect={false} aria-label={t('dashboards.display.seriesPick')}
                data={options(o.match)} value={o.match || null} onChange={(v) => v && edit(i, { match: v })} />
              <ActionIcon variant="subtle" color="gray" aria-label={t('dashboards.display.remove')} onClick={() => setRows(rows.filter((_, k) => k !== i))}>
                <IconX size={14} />
              </ActionIcon>
            </Group>
            <Group gap={6} wrap="nowrap" align="center">
              <TextInput size="xs" style={{ flex: 1 }} maxLength={40} aria-label={t('dashboards.display.seriesName')} placeholder={t('dashboards.display.seriesName')}
                value={o.name ?? ''} onChange={(e) => edit(i, { name: e.currentTarget.value || undefined })} />
              <Select size="xs" w={120} allowDeselect={false} aria-label={t('dashboards.display.colour')} data={colours} value={o.colour ?? 'auto'}
                leftSection={o.colour ? <span className="fb-swatch" style={{ background: seriesColour(o.colour) }} /> : undefined}
                onChange={(v) => edit(i, { colour: v && v !== 'auto' ? (v as SeriesColour) : undefined })} />
              <Checkbox size="xs" label={t('dashboards.display.hide')} checked={!!o.hide} onChange={(e) => edit(i, { hide: e.currentTarget.checked || undefined })} />
            </Group>
          </Stack>
        ))}
        <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} w="fit-content"
          disabled={rows.length >= MAX_OVERRIDES || !free} onClick={() => free && setRows([...rows, { match: free }])}>
          {t('dashboards.display.addSeries')}
        </Button>
      </Stack>
    </div>
  )
}
