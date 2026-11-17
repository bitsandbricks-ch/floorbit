import { ActionIcon, Button, Checkbox, Group, NumberInput, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { IconArrowsMove, IconLayoutRows, IconPlus, IconX } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { SeatViewData } from '@/api/types'
import { type Gap, GAP_MAX, GAP_MIN, cleanGaps, freeGapSpot } from './gaps'
import type { ItemRef } from './geometry'

interface StoredBlock {
  id: string; cols: number; rows: number; naming?: string; row_start?: string; row_labels?: string; reverse_numbers?: boolean
  col_gaps?: Gap[]; row_gaps?: Gap[]; seat_at?: Record<string, [number, number]> | null
}
type Change = (ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => Promise<void>

/** A seat block's size, seat names and gaps, from the block as the server keeps it (the drawing
 *  has only cells). Each field is saved on its own, as one step to undo. */
export function BlockFields({ data, item, onChange, arranging = false, onArrange }: {
  data: SeatViewData; item: ItemRef; onChange: Change
  /** Seat handles are out, so seats can be dragged one by one (SeatHandles.tsx). */
  arranging?: boolean
  onArrange?: (on: boolean) => void
}) {
  const { t } = useTranslation()
  const blocks = useQuery({
    queryKey: qk.planBlocks(data.hall),
    queryFn: () => get<StoredBlock[]>(`/api/seat-blocks?hall=${encodeURIComponent(data.hall)}`),
  })
  const block = blocks.data?.find((b) => b.id === item.id)
  const [cols, setCols] = useState<number | null>(null)
  const [rows, setRows] = useState<number | null>(null)
  const [rowStart, setRowStart] = useState<string | null>(null)
  if (!block) return null
  const save = (before: Record<string, unknown>, after: Record<string, unknown>) => {
    if (JSON.stringify(before) !== JSON.stringify(after)) void onChange(item, before, after).then(() => blocks.refetch())
  }
  const size = (field: 'cols' | 'rows', v: number | null) => { if (v) save({ [field]: block[field] }, { [field]: v }) }
  const naming = block.naming || 'block'
  const start = block.row_start || 'A'
  const saveStart = () => { if (rowStart) save({ row_start: start }, { row_start: rowStart.toUpperCase() }) }
  return (
    <>
      <SimpleGrid cols={2}>
        <NumberInput label={t('plan.edit.block.cols')} min={1} max={200} value={cols ?? block.cols} onChange={(v) => setCols(Number(v) || null)}
          onBlur={() => size('cols', cols)} onKeyDown={(e) => { if (e.key === 'Enter') size('cols', cols) }} />
        <NumberInput label={t('plan.edit.block.rows')} min={1} max={50} value={rows ?? block.rows} onChange={(v) => setRows(Number(v) || null)}
          onBlur={() => size('rows', rows)} onKeyDown={(e) => { if (e.key === 'Enter') size('rows', rows) }} />
      </SimpleGrid>
      <Select label={t('plan.edit.block.naming')} allowDeselect={false} value={naming} onChange={(v) => v && save({ naming }, { naming: v })}
        data={[{ value: 'rows', label: t('plan.edit.block.namingRows') }, { value: 'block', label: t('plan.edit.block.namingBlock') }]} />
      {naming === 'rows' && (
        <SimpleGrid cols={2}>
          <TextInput label={t('plan.edit.block.rowStart')} value={rowStart ?? start} maxLength={2}
            onChange={(e) => setRowStart(e.currentTarget.value.replace(/[^a-z]/gi, ''))}
            onBlur={saveStart} onKeyDown={(e) => { if (e.key === 'Enter') saveStart() }} />
          <Select label={t('plan.edit.block.rowLabels')} allowDeselect={false} value={block.row_labels || 'start'}
            onChange={(v) => v && save({ row_labels: block.row_labels || 'start' }, { row_labels: v })}
            data={['start', 'end', 'both', 'none'].map((x) => ({ value: x, label: t(`plan.edit.block.labels.${x}`) }))} />
        </SimpleGrid>
      )}
      {onArrange && (
        <div>
          <Group gap="xs" wrap="nowrap">
            <Button size="xs" variant={arranging ? 'filled' : 'default'} leftSection={<IconArrowsMove size={14} />} aria-pressed={arranging}
              onClick={() => onArrange(!arranging)}>{t(arranging ? 'plan.edit.seats.done' : 'plan.edit.seats.arrange')}</Button>
            {block.seat_at && (
              <Button size="xs" variant="subtle" leftSection={<IconLayoutRows size={14} />}
                onClick={() => { onArrange(false); save({ seat_at: block.seat_at }, { seat_at: null }) }}>{t('plan.edit.seats.rows')}</Button>
            )}
          </Group>
          <Text size="xs" c="dimmed" mt={4}>{t(arranging ? 'plan.edit.seats.hint' : block.seat_at ? 'plan.edit.seats.free' : 'plan.edit.seats.intro')}</Text>
        </div>
      )}
      <Checkbox label={t('plan.edit.block.reverse')} checked={!!block.reverse_numbers}
        onChange={(e) => save({ reverse_numbers: !!block.reverse_numbers }, { reverse_numbers: e.currentTarget.checked })} />
      <GapList kind="col" gaps={block.col_gaps ?? []} count={block.cols} onSave={(next) => save({ col_gaps: block.col_gaps ?? [] }, { col_gaps: cleanGaps(next, block.cols) })} />
      <GapList kind="row" gaps={block.row_gaps ?? []} count={block.rows} onSave={(next) => save({ row_gaps: block.row_gaps ?? [] }, { row_gaps: cleanGaps(next, block.rows) })} />
    </>
  )
}

/** Room in every row after a column (fiber rolls), or a lane after a row; seat numbers carry on across. */
function GapList({ kind, gaps, count, onSave }: { kind: 'col' | 'row'; gaps: Gap[]; count: number; onSave: (gaps: Gap[]) => void }) {
  const { t } = useTranslation()
  const spot = freeGapSpot(gaps, count)
  const set = (i: number, g: Partial<Gap>) => onSave(gaps.map((x, k) => (k === i ? { ...x, ...g } : x)))
  return (
    <div>
      <Group justify="space-between" mb={4} wrap="nowrap">
        <Text size="sm" fw={500}>{t(`plan.edit.gaps.${kind}`)}</Text>
        <Button size="compact-xs" variant="subtle" leftSection={<IconPlus size={12} />} disabled={spot == null}
          onClick={() => spot != null && onSave([...gaps, { after: spot, size: kind === 'row' ? 2 : 1 }])}>{t('plan.edit.gaps.add')}</Button>
      </Group>
      {!gaps.length && <Text size="xs" c="dimmed">{t(`plan.edit.gaps.none_${kind}`)}</Text>}
      <Stack gap={6}>
        {gaps.map((g, i) => (
          <Group key={`${g.after}-${i}`} gap="xs" wrap="nowrap" align="flex-end">
            <NumberInput size="xs" style={{ flex: 1 }} label={t(`plan.edit.gaps.after_${kind}`)} min={1} max={count - 1} defaultValue={g.after}
              onBlur={(e) => set(i, { after: Number(e.currentTarget.value) || g.after })} />
            <NumberInput size="xs" style={{ flex: 1 }} label={t(`plan.edit.gaps.size_${kind}`)} min={GAP_MIN} max={GAP_MAX} step={0.5} decimalScale={2} defaultValue={g.size}
              onBlur={(e) => set(i, { size: Number(e.currentTarget.value) || g.size })} />
            <ActionIcon variant="subtle" color="gray" mb={4} aria-label={t('plan.edit.gaps.remove')} onClick={() => onSave(gaps.filter((_, k) => k !== i))}>
              <IconX size={14} />
            </ActionIcon>
          </Group>
        ))}
      </Stack>
    </div>
  )
}
