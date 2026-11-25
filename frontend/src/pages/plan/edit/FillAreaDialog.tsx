import { Button, Checkbox, Group, Modal, NumberInput, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { WALKWAY_DEFAULT, WALKWAY_MAX } from '../lineMarks'
import { nextFreeRow } from './tools'

/** A box on the plan in % of it, its top left corner first. */
export interface AreaBox { x: number; y: number; w: number; h: number }

/** What POST /api/seat-blocks/fill takes besides the box (floorbit/fill_area.py, #1565). */
export interface FillOptions { seats: number; rows: number; spacer: number; walkway: number; row_start: string; labels: boolean }

interface Preview { blocks: number; marks: number; seats: number }

/** Fill area: the box just drawn, filled with runs of seats and the walkways between them. */
export function FillAreaDialog({ box, hall, onClose, onFill }: {
  box: AreaBox | null; hall: string; onClose: () => void
  onFill: (opts: FillOptions) => Promise<boolean>
}) {
  const { t } = useTranslation()
  const blocks = useQuery({ queryKey: qk.seatBlocks, queryFn: () => get<{ naming?: string; row_start?: string; rows?: number; name?: string }[]>('/api/seat-blocks'), enabled: !!box })
  if (!box) return null
  if (!blocks.data) return <Modal opened onClose={onClose} title={t('fillArea.title')}><Text c="dimmed">…</Text></Modal>
  return <FillForm box={box} hall={hall} row={nextFreeRow(blocks.data)} onClose={onClose} onFill={onFill} />
}

function FillForm({ box, hall, row, onClose, onFill }: {
  box: AreaBox; hall: string; row: string; onClose: () => void; onFill: (opts: FillOptions) => Promise<boolean>
}) {
  const { t } = useTranslation()
  const [v, setV] = useState<FillOptions>({ seats: 10, rows: 2, spacer: 1, walkway: WALKWAY_DEFAULT, row_start: row, labels: true })
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof FillOptions>(k: K, val: FillOptions[K]) => setV((o) => ({ ...o, [k]: val }))
  const opts = { ...v, row_start: (v.row_start.trim() || 'A').toUpperCase() }
  const [asked] = useDebouncedValue(opts, 250)
  const preview = useQuery({
    queryKey: qk.fillPreview(hall, { ...box, ...asked }), placeholderData: keepPreviousData, retry: false,
    queryFn: () => post<Preview>('/api/seat-blocks/fill', { ...box, ...asked, hall_id: hall, preview: true }),
  })
  const submit = async () => {
    setBusy(true)
    try {
      await onFill(opts)
    } finally {
      setBusy(false)
    }
  }
  const count = preview.data && !preview.isError ? preview.data : null
  return (
    <Modal opened onClose={onClose} title={t('fillArea.title')}>
      <form onSubmit={(e) => { e.preventDefault(); void submit() }}>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">{t('fillArea.intro')}</Text>
          <SimpleGrid cols={2}>
            <NumberInput label={t('fillArea.seats')} min={1} max={200} allowDecimal={false} value={v.seats}
              onChange={(x) => set('seats', Math.max(1, Number(x) || 1))} data-autofocus />
            <NumberInput label={t('fillArea.rows')} description={t('fillArea.rowsHint')} min={1} max={50} allowDecimal={false} value={v.rows}
              onChange={(x) => set('rows', Math.max(1, Number(x) || 1))} />
          </SimpleGrid>
          <SimpleGrid cols={2}>
            <NumberInput label={t('rowSpacers.newSpacer')} min={0} max={20} step={0.5} decimalScale={2} disabled={v.rows < 2}
              suffix={` ${t('rowSpacers.unit', { count: v.spacer })}`} value={v.spacer} onChange={(x) => set('spacer', Math.min(20, Math.max(0, Number(x) || 0)))} />
            <NumberInput label={t('fillArea.walkway')} description={t('fillArea.walkwayHint')} min={0} max={WALKWAY_MAX} step={0.5} decimalScale={2}
              suffix={` ${t('rowSpacers.unit', { count: v.walkway })}`} value={v.walkway} onChange={(x) => set('walkway', Math.min(WALKWAY_MAX, Math.max(0, Number(x) || 0)))} />
          </SimpleGrid>
          <SimpleGrid cols={2}>
            <TextInput label={t('plan.edit.block.rowStart')} value={v.row_start} maxLength={2}
              onChange={(e) => set('row_start', e.currentTarget.value.replace(/[^a-z]/gi, ''))} />
            <Checkbox mt="lg" label={t('fillArea.labels')} checked={v.labels} onChange={(e) => set('labels', e.currentTarget.checked)} />
          </SimpleGrid>
          <Text size="sm" c={preview.isError ? 'down' : 'dimmed'} aria-live="polite">
            {preview.isError
              ? (preview.error instanceof Error ? preview.error.message : t('fillArea.tooSmall'))
              : count ? t('fillArea.preview', { count: count.blocks, seats: count.seats, walkways: count.marks }) : '…'}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" loading={busy} disabled={!count || preview.isError}>{t('fillArea.create')}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
