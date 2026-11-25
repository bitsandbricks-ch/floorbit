import { ActionIcon, Badge, Button, Checkbox, Group, Input, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, UnstyledButton } from '@mantine/core'
import { IconArrowsMove, IconChevronDown, IconChevronUp, IconFlipHorizontal, IconFlipVertical, IconLayoutRows, IconPlus, IconX } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { SeatViewData } from '@/api/types'
import { RowSeatStrip } from './RowSeatStrip'
import type { ItemRef } from './geometry'
import { mirrorBlock } from './rowShapes'
import { type BlockRow, MAX_ROWS, MAX_SEATS, ROW_LABELS, type RowLabel, type RowShape, SHAPES, moveRow, newRow, withLabel, withSeats, withShape, withUSide } from './rows'
import { withCables } from './autoChairs'
import { BlockCableFields, CablesConnect } from './CableFields'
import { PieceFields } from './PieceFields'
import { RowTabs } from './RowTabs'
import './BlockFields.css'

interface StoredBlock {
  id: string; rows: BlockRow[]; row_names?: string[]; naming?: string; row_start?: string; row_labels?: string; reverse_numbers?: boolean
  seat_at?: Record<string, [number, number]> | null
}
type Change = (ref: ItemRef, before: Record<string, unknown>, after: Record<string, unknown>) => Promise<void>

/** A seat block's naming and its rows (floorbit/seat_rows.py): a block is a list of rows, each with
 *  its own seats, shape and space above it, from the block as the server keeps it (the drawing has
 *  only cells). Each change is saved on its own, as one step to undo. */
export function BlockFields({ data, item, onChange, arranging = false, onArrange, picked: pickedProp, onPick, section }: {
  data: SeatViewData; item: ItemRef; onChange: Change
  /** One of the panel's tabs (Block, Rows, Seats); all of them when left out. */
  section?: 'block' | 'rows' | 'seats'
  /** The picked row's id, when the editor keeps it (a double-click on the plan picks one). */
  picked?: string | null
  onPick?: (id: string | null) => void
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
  const [rowStart, setRowStart] = useState<string | null>(null)
  const [own, setOwn] = useState<string | null>(null)
  const picked = pickedProp !== undefined ? pickedProp : own
  const setPicked = onPick ?? setOwn
  if (!block || !Array.isArray(block.rows)) return null
  const save = (before: Record<string, unknown>, after: Record<string, unknown>) => {
    if (JSON.stringify(before) !== JSON.stringify(after)) void onChange(item, before, after).then(() => blocks.refetch())
  }
  const saveRows = (next: BlockRow[]) => save({ rows: block.rows }, { rows: next })
  const naming = block.naming || 'block'
  const start = block.row_start || 'A'
  const saveStart = () => { if (rowStart) save({ row_start: start }, { row_start: rowStart.toUpperCase() }) }
  const rowName = (i: number) => block.row_names?.[i] ?? String(i + 1)
  const open = block.rows.findIndex((r) => r.id === picked)
  const rotation = data.drawing?.shapes.find((b) => b.id === item.id)?.rotation ?? 0
  // Upside down is mirrored and turned half round, so the rows keep their order and names.
  const turnBlock = (flip: boolean) => save(
    { rows: block.rows, seat_at: block.seat_at ?? null, ...(flip ? { rotation } : {}) },
    { ...mirrorBlock(block), ...(flip ? { rotation: (rotation + 180) % 360 } : {}) },
  )
  const show = (part: 'block' | 'rows' | 'seats') => !section || section === part
  // In the Rows tab a row is always open: the first one until another is picked.
  const shown = section === 'rows' && open < 0 ? 0 : open
  return (
    <>
      {show('seats') && (
        <>
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
        </>
      )}
      {show('block') && (
        <Group gap="xs" wrap="nowrap">
          <Button size="xs" variant="default" leftSection={<IconFlipVertical size={14} />} onClick={() => turnBlock(false)}>{t('blockRows.mirrorBlock')}</Button>
          <Button size="xs" variant="default" leftSection={<IconFlipHorizontal size={14} />} onClick={() => turnBlock(true)}>{t('blockRows.flipBlock')}</Button>
        </Group>
      )}
      {show('block') && !block.seat_at && <BlockCableFields rows={block.rows} onSave={saveRows} />}
      {show('rows') && (
        <>
          {section === 'rows'
            ? <RowTabs rows={block.rows} name={rowName} picked={block.rows[shown]?.id ?? null} onPick={setPicked} onSave={saveRows} />
            : <RowList rows={block.rows} name={rowName} picked={picked} onPick={setPicked} onSave={saveRows} />}
          {block.rows.length > 1 && !block.seat_at && <Text size="xs" c="dimmed">{t('blockRows.planHint')}</Text>}
          {shown >= 0 && (
            <RowFields key={block.rows[shown].id} row={block.rows[shown]} name={rowName(shown)} first={shown === 0} letters={naming === 'rows'}
              onSave={(row) => saveRows(block.rows.map((r, i) => (i === shown ? row : r)))} />
          )}
        </>
      )}
      {show('seats') && onArrange && (
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
      {show('seats') && (
        <Checkbox label={t('plan.edit.block.reverse')} checked={!!block.reverse_numbers}
          onChange={(e) => save({ reverse_numbers: !!block.reverse_numbers }, { reverse_numbers: e.currentTarget.checked })} />
      )}
    </>
  )
}

/** The block's rows, top first, with the space above each: pick one to change it, move it, or
 *  take it out; add one under the others. */
function RowList({ rows, name, picked, onPick, onSave }: {
  rows: BlockRow[]; name: (i: number) => string; picked: string | null
  onPick: (id: string | null) => void; onSave: (rows: BlockRow[]) => void
}) {
  const { t } = useTranslation()
  const setGap = (i: number, gap: number) => onSave(rows.map((r, k) => (k === i ? { ...r, gap } : r)))
  return (
    <div>
      <Group justify="space-between" mb={4} wrap="nowrap">
        <Text size="sm" fw={500}>{t('blockRows.title', { count: rows.length })}</Text>
        <Button size="compact-xs" variant="subtle" leftSection={<IconPlus size={12} />} disabled={rows.length >= MAX_ROWS}
          onClick={() => { const row = newRow(rows); onSave([...rows, row]); onPick(row.id) }}>{t('blockRows.add')}</Button>
      </Group>
      <Stack gap={0} className="fb-block-rows">
        {rows.map((r, i) => (
          <div key={r.id}>
            {i > 0 && (
              <Group gap="xs" wrap="nowrap" className="fb-row-gap">
                <Text size="xs" c="dimmed" style={{ flex: 1 }}>{t('blockRows.gapAbove', { name: name(i) })}</Text>
                <NumberInput key={r.gap} size="xs" w={88} min={0} max={20} step={0.5} decimalScale={2} aria-label={t('blockRows.gapAboveLabel', { name: name(i) })}
                  defaultValue={r.gap} suffix={` ${t('blockRows.seatsUnit')}`}
                  onBlur={(e) => { const v = Number(e.currentTarget.value.replace(/[^\d.]/g, '')); if (Number.isFinite(v) && v !== r.gap) setGap(i, Math.min(20, Math.max(0, v))) }} />
              </Group>
            )}
            <Group gap={6} wrap="nowrap" className={picked === r.id ? 'fb-row on' : 'fb-row'}>
              <UnstyledButton style={{ flex: 1, minWidth: 0 }} aria-pressed={picked === r.id} onClick={() => onPick(picked === r.id ? null : r.id)}
                aria-label={t('blockRows.pick', { name: name(i) })}>
                <Group gap={8} wrap="nowrap">
                  <Badge variant="light" color="gray" radius="sm" miw={30}>{name(i)}</Badge>
                  <Text size="xs" truncate>{t('blockRows.summary', { count: r.seats, shape: t(`blockRows.shapes.${r.shape}`) })}</Text>
                </Group>
              </UnstyledButton>
              <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === 0} aria-label={t('blockRows.up', { name: name(i) })}
                onClick={() => onSave(moveRow(rows, i, i - 1))}><IconChevronUp size={14} /></ActionIcon>
              <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === rows.length - 1} aria-label={t('blockRows.down', { name: name(i) })}
                onClick={() => onSave(moveRow(rows, i, i + 1))}><IconChevronDown size={14} /></ActionIcon>
              <ActionIcon size="sm" variant="subtle" color="gray" disabled={rows.length === 1} aria-label={t('blockRows.remove', { name: name(i) })}
                onClick={() => { onSave(rows.filter((_, k) => k !== i)); if (picked === r.id) onPick(null) }}><IconX size={14} /></ActionIcon>
            </Group>
          </div>
        ))}
      </Stack>
    </div>
  )
}

/** One row: its seats, shape, where it sits sideways, where people sit, numbering and gaps. */
function RowFields({ row, name, first, letters, onSave }: {
  row: BlockRow; name: string; first: boolean
  /** The block names its rows, so each has a letter on the plan. */
  letters: boolean
  onSave: (row: BlockRow) => void
}) {
  const { t } = useTranslation()
  const [seats, setSeats] = useState<number | null>(null)
  const saveSeats = () => { if (seats && seats !== row.seats) onSave(withSeats(row, seats)) }
  const num = (v: string, lo: number, hi: number) => { const n = Number(v.replace(/[^\d.-]/g, '')); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : null }
  return (
    <Stack gap="xs" className="fb-row-fields">
      <Text size="sm" fw={600}>{t('blockRows.rowTitle', { name })}</Text>
      <RowSeatStrip seats={row.seats} gaps={row.col_gaps} onSave={(col_gaps) => onSave({ ...row, col_gaps })} />
      <NumberInput label={t('blockRows.seats')} min={1} max={MAX_SEATS} value={seats ?? row.seats} onChange={(v) => setSeats(Number(v) || null)}
        onBlur={saveSeats} onKeyDown={(e) => { if (e.key === 'Enter') saveSeats() }} />
      <Select label={t('blockRows.shape')} allowDeselect={false} value={row.shape} onChange={(v) => v && v !== row.shape && onSave(withShape(row, v as RowShape))}
        data={SHAPES.map((s) => ({ value: s, label: t(`blockRows.shapes.${s}`) }))} />
      {row.shape === 'arc' && (
        <NumberInput label={t('blockRows.bend')} description={t('blockRows.bendHint')} min={-330} max={330} step={15} defaultValue={row.bend ?? 60} suffix="°"
          onBlur={(e) => { const v = num(e.currentTarget.value, -330, 330); if (v != null && v !== row.bend) onSave({ ...row, bend: v }) }} />
      )}
      {row.shape === 'u' && row.sides?.length === 3 && (
        <div>
          <SimpleGrid cols={2} spacing="xs">
            {([0, 2] as const).map((i) => (
              <NumberInput key={`u-${i}-${row.sides![i]}`} size="xs" label={t(`blockRows.side_u_${i}`)} min={0} max={row.seats} defaultValue={row.sides![i]}
                onBlur={(e) => {
                  const v = num(e.currentTarget.value, 0, row.seats)
                  if (v != null && v !== row.sides![i]) onSave(withUSide(row, i, v))
                }} />
            ))}
          </SimpleGrid>
          <Text size="xs" c="dimmed" mt={4}>{t('blockRows.uMiddle', { count: row.sides[1], total: row.seats })}</Text>
        </div>
      )}
      {row.shape === 'l' && row.sides && (
        <div>
          <SimpleGrid cols={row.sides.length} spacing="xs">
            {row.sides.map((n, i) => (
              <NumberInput key={`${row.shape}-${i}`} size="xs" label={t(`blockRows.side_${row.shape}_${i}`)} min={0} max={row.seats} defaultValue={n}
                onBlur={(e) => {
                  const v = num(e.currentTarget.value, 0, row.seats)
                  if (v == null || v === n || !row.sides) return
                  // The other arm gives or takes seats so the row keeps its count.
                  const sides = [...row.sides]
                  const other = 1 - i
                  const moved = Math.min(v - n, sides[other])
                  sides[i] = n + moved
                  sides[other] -= moved
                  onSave({ ...row, sides })
                }} />
            ))}
          </SimpleGrid>
          <Text size="xs" c="dimmed" mt={4}>{t('blockRows.sidesHint', { count: row.seats })}</Text>
        </div>
      )}
      {row.shape === 'path' && <PieceFields row={row} onSave={onSave} />}
      <Group gap="xs" wrap="nowrap">
        <Button size="xs" variant={row.mirror ? 'light' : 'default'} aria-pressed={!!row.mirror} leftSection={<IconFlipVertical size={14} />}
          onClick={() => onSave({ ...row, mirror: !row.mirror })}>{t('blockRows.mirror')}</Button>
        <Button size="xs" variant={row.flip ? 'light' : 'default'} aria-pressed={!!row.flip} leftSection={<IconFlipHorizontal size={14} />}
          onClick={() => onSave({ ...row, flip: !row.flip })}>{t('blockRows.flip')}</Button>
      </Group>
      {row.shape !== 'line' && <Text size="xs" c="dimmed">{t('blockRows.shapeHint')}</Text>}
      <Input.Wrapper label={t('blockRows.align')}>
        <SegmentedControl fullWidth size="xs" value={row.align} onChange={(v) => onSave({ ...row, align: v as BlockRow['align'] })}
          data={(['start', 'middle', 'end'] as const).map((v) => ({ value: v, label: t(`blockRows.aligns.${v}`) }))} />
      </Input.Wrapper>
      <SimpleGrid cols={2} spacing="xs">
        <NumberInput size="xs" label={t('blockRows.shift')} min={-200} max={200} step={0.5} decimalScale={2} defaultValue={row.shift}
          onBlur={(e) => { const v = num(e.currentTarget.value, -200, 200); if (v != null && v !== row.shift) onSave({ ...row, shift: v }) }} />
        <Select size="xs" label={t('seatCables.chairs')} allowDeselect={false} value={row.side || 'auto'}
          onChange={(v) => v && onSave({ ...row, side: v === 'auto' ? '' : (v as 'left' | 'right') })}
          data={['auto', 'left', 'right'].map((v) => ({ value: v, label: t(`blockRows.sides.${v}`) }))} />
      </SimpleGrid>
      {row.shape === 'line' && <CablesConnect value={row.cables ?? ''} onChange={(v) => onSave(withCables([row], v)[0])} />}
      {first && <Text size="xs" c="dimmed">{t('blockRows.firstGap')}</Text>}
      {letters && (
        <Select size="xs" label={t('blockRows.rowLabel')} description={t('blockRows.rowLabelHint')} allowDeselect={false} value={row.label || 'block'}
          onChange={(v) => v && v !== (row.label || 'block') && onSave(withLabel(row, v === 'block' ? '' : (v as RowLabel)))}
          data={['block', ...ROW_LABELS, ...(row.label === 'moved' ? ['moved'] : [])].map((v) => ({ value: v, label: t(`blockRows.rowLabels.${v}`) }))} />
      )}
      <Checkbox label={t('blockRows.reverse')} checked={row.reverse} onChange={(e) => onSave({ ...row, reverse: e.currentTarget.checked })} />
    </Stack>
  )
}
