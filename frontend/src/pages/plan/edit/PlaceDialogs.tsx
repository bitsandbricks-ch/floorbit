import { Button, Checkbox, Collapse, Group, Modal, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, UnstyledButton } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { blockStep, nextFreeRow } from './tools'

interface Defaults { naming?: string; row_labels?: string; reverse_numbers?: boolean; block_gap?: number }

/** The values of a new seat block, as POST /api/seat-blocks takes them (static/js/editor/modals.js). */
export interface NewBlock {
  naming: string; row_start: string; row_labels: string; name: string; cols: number; rows: number
  numbering_pattern: 'blockname_number'; reverse_numbers: boolean; rotation: number
}

/** New seat block(s) where the plan was clicked. Spacing and the rest start from Settings > Floor plan. */
export function PlaceBlockDialog({ opened, onClose, onCreate }: {
  opened: boolean; onClose: () => void
  onCreate: (block: NewBlock, copies: { count: number; dx: number; dy: number } | null) => Promise<void>
}) {
  const { t } = useTranslation()
  const config = useQuery({ queryKey: qk.appConfig, queryFn: () => get<{ floorplan_defaults?: Defaults }>('/api/config'), staleTime: 60_000, enabled: opened })
  const blocks = useQuery({ queryKey: qk.seatBlocks, queryFn: () => get<{ naming?: string; row_start?: string; rows?: number; name?: string }[]>('/api/seat-blocks'), enabled: opened })
  if (!opened || !config.data || !blocks.data) return <Modal opened={opened} onClose={onClose} title={t('plan.edit.block.title')}><Text c="dimmed">…</Text></Modal>
  return <BlockForm key="form" defaults={config.data.floorplan_defaults ?? {}} row={nextFreeRow(blocks.data)} onClose={onClose} onCreate={onCreate} />
}

function BlockForm({ defaults, row, onClose, onCreate }: {
  defaults: Defaults; row: string; onClose: () => void
  onCreate: (block: NewBlock, copies: { count: number; dx: number; dy: number } | null) => Promise<void>
}) {
  const { t } = useTranslation()
  const [v, setV] = useState({
    naming: defaults.naming || 'rows', row_start: row, row_labels: defaults.row_labels || 'start', name: '', cols: 8, rows: 1,
    reverse_numbers: !!defaults.reverse_numbers, rotation: 0, count: 1, direction: 'down' as 'down' | 'right', gap: defaults.block_gap ?? 3,
  })
  const [more, setMore] = useState(false)
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof typeof v>(k: K, val: (typeof v)[K]) => setV((o) => ({ ...o, [k]: val }))
  const rowsNamed = v.naming === 'rows'
  const seats = v.cols * v.rows
  const submit = async () => {
    setBusy(true)
    try {
      const block: NewBlock = {
        naming: v.naming, row_start: (v.row_start.trim() || 'A').toUpperCase(), row_labels: v.row_labels, name: v.name.trim(),
        cols: Math.max(1, v.cols), rows: Math.max(1, v.rows), numbering_pattern: 'blockname_number', reverse_numbers: v.reverse_numbers, rotation: v.rotation,
      }
      await onCreate(block, v.count > 1 ? { count: v.count, ...blockStep(block, v.gap, v.direction) } : null)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal opened onClose={onClose} title={t('plan.edit.block.title')}>
      <form onSubmit={(e) => { e.preventDefault(); void submit() }}>
        <Stack gap="sm">
          <Select label={t('plan.edit.block.naming')} allowDeselect={false} value={v.naming} onChange={(x) => set('naming', x ?? 'rows')}
            data={[{ value: 'rows', label: t('plan.edit.block.namingRows') }, { value: 'block', label: t('plan.edit.block.namingBlock') }]} />
          <TextInput label={t('plan.edit.block.name')} description={rowsNamed ? t('plan.edit.block.nameRows') : t('plan.edit.block.nameBlock')}
            placeholder="A" value={v.name} maxLength={40} onChange={(e) => set('name', e.currentTarget.value)} data-autofocus />
          <SimpleGrid cols={3}>
            <NumberInput label={t('plan.edit.block.cols')} min={1} max={200} value={v.cols} onChange={(x) => set('cols', Number(x) || 1)} />
            <NumberInput label={t('plan.edit.block.rows')} min={1} max={50} value={v.rows} onChange={(x) => set('rows', Number(x) || 1)} />
            <NumberInput label={t('plan.edit.block.count')} min={1} max={30} value={v.count} onChange={(x) => set('count', Math.min(30, Number(x) || 1))} />
          </SimpleGrid>
          <UnstyledButton onClick={() => setMore((m) => !m)} aria-expanded={more}>
            <Text size="sm" c="bit">{more ? '▾' : '▸'} {t('plan.edit.block.more')}</Text>
          </UnstyledButton>
          <Collapse expanded={more}>
            <Stack gap="sm">
              {rowsNamed && (
                <SimpleGrid cols={2}>
                  <TextInput label={t('plan.edit.block.rowStart')} value={v.row_start} maxLength={2} onChange={(e) => set('row_start', e.currentTarget.value.replace(/[^a-z]/gi, ''))} />
                  <Select label={t('plan.edit.block.rowLabels')} allowDeselect={false} value={v.row_labels} onChange={(x) => set('row_labels', x ?? 'start')}
                    data={['start', 'end', 'both', 'none'].map((x) => ({ value: x, label: t(`plan.edit.block.labels.${x}`) }))} />
                </SimpleGrid>
              )}
              <div>
                <Text size="sm" fw={500} mb={4}>{t('plan.edit.rotation')}</Text>
                <SegmentedControl fullWidth value={String(v.rotation)} onChange={(x) => set('rotation', Number(x))}
                  data={['0', '90', '180', '270'].map((x) => ({ value: x, label: `${x}°` }))} />
              </div>
              <Checkbox label={t('plan.edit.block.reverse')} checked={v.reverse_numbers} onChange={(e) => set('reverse_numbers', e.currentTarget.checked)} />
              {v.count > 1 && (
                <SimpleGrid cols={2}>
                  <Select label={t('plan.edit.block.direction')} allowDeselect={false} value={v.direction} onChange={(x) => set('direction', (x as 'down' | 'right') ?? 'down')}
                    data={[{ value: 'down', label: t('plan.edit.block.down') }, { value: 'right', label: t('plan.edit.block.right') }]} />
                  <NumberInput label={t('plan.edit.block.gap')} min={0} max={50} suffix=" %" value={v.gap} onChange={(x) => set('gap', Number(x) || 0)} />
                </SimpleGrid>
              )}
              <Text size="xs" c="dimmed">{t('plan.edit.block.defaults')} <a href="/settings#sec-floorplan">{t('plan.edit.block.defaultsLink')}</a></Text>
            </Stack>
          </Collapse>
          <Text size="sm" c="dimmed">
            {rowsNamed
              ? t('plan.edit.block.previewRows', { count: seats * v.count, row: (v.row_start || 'A').toUpperCase(), cols: v.cols })
              : t('plan.edit.block.previewBlock', { count: seats * v.count, name: v.name || 'A', last: seats })}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" loading={busy}>{t('plan.edit.block.create', { count: v.count })}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

/** A label's text or an icon, where the plan was clicked. */
export function PlaceMarkDialog({ kind, onClose, onCreate }: {
  kind: 'text' | 'icon' | null; onClose: () => void; onCreate: (body: Record<string, unknown>) => Promise<void>
}) {
  const { t } = useTranslation()
  const icons = useQuery({ queryKey: qk.planIcons, queryFn: () => get<{ icons: Record<string, string[]> }>('/api/plan-marks?hall=-'), enabled: kind === 'icon', staleTime: Infinity })
  const [text, setText] = useState('')
  const [icon, setIcon] = useState<string | null>(null)
  const [size, setSize] = useState('m')
  const [busy, setBusy] = useState(false)
  const close = () => { setText(''); setIcon(null); onClose() }
  const submit = async () => {
    if (kind === 'text' ? !text.trim() : !icon) return
    setBusy(true)
    try {
      await onCreate(kind === 'text' ? { kind, text: text.trim(), size } : { kind, icon, size })
      setText(''); setIcon(null)
    } finally {
      setBusy(false)
    }
  }
  const names = Object.keys(icons.data?.icons ?? {})
  return (
    <Modal opened={!!kind} onClose={close} title={t(kind === 'icon' ? 'plan.edit.mark.iconTitle' : 'plan.edit.mark.textTitle')}>
      <form onSubmit={(e) => { e.preventDefault(); void submit() }}>
        <Stack gap="sm">
          {kind === 'text'
            ? <TextInput label={t('plan.edit.text')} value={text} maxLength={60} onChange={(e) => setText(e.currentTarget.value)} data-autofocus required />
            : (
              <Select label={t('plan.edit.mark.icon')} searchable value={icon} onChange={setIcon} data-autofocus nothingFoundMessage={t('plan.edit.mark.none')}
                data={names.map((n) => ({ value: n, label: t(`plan.edit.icons.${n}`, { defaultValue: n.replace(/[-_]/g, ' ') }) }))}
                renderOption={({ option }) => <Group gap="xs" wrap="nowrap"><IconGlyph paths={icons.data?.icons[option.value] ?? []} />{option.label}</Group>} />
            )}
          <div>
            <Text size="sm" fw={500} mb={4}>{t('plan.edit.mark.size')}</Text>
            <SegmentedControl fullWidth value={size} onChange={setSize}
              data={['s', 'm', 'l'].map((x) => ({ value: x, label: t(`plan.edit.mark.sizes.${x}`) }))} />
          </div>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>{t('common.cancel')}</Button>
            <Button type="submit" loading={busy} disabled={kind === 'text' ? !text.trim() : !icon}>{t('plan.edit.mark.place')}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

function IconGlyph({ paths }: { paths: string[] }) {
  return (
    <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths.map((d, i) => <path key={i} d={d} />)}
    </svg>
  )
}
