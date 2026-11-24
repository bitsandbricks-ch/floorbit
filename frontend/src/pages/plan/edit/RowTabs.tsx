import { ActionIcon, Group, NumberInput, Text, Tooltip, UnstyledButton } from '@mantine/core'
import { IconChevronLeft, IconChevronRight, IconPlus, IconX } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { type BlockRow, MAX_ROWS, moveRow, newRow } from './rows'
import './RowTabs.css'

/** A block's rows as small tabs, one per row (Mike picked tabs and sub tabs for the panel), with the
 *  picked row's place in the block and the space above it. The picked row's fields come below. */
export function RowTabs({ rows, name, picked, onPick, onSave }: {
  rows: BlockRow[]; name: (i: number) => string; picked: string | null
  onPick: (id: string | null) => void; onSave: (rows: BlockRow[]) => void
}) {
  const { t } = useTranslation()
  const i = rows.findIndex((r) => r.id === picked)
  const r = i >= 0 ? rows[i] : null
  return (
    <div>
      <div role="tablist" aria-label={t('blockRows.title', { count: rows.length })} className="fb-row-tabs">
        {rows.map((row, k) => (
          <Tooltip key={row.id} label={t('blockRows.summary', { count: row.seats, shape: t(`blockRows.shapes.${row.shape}`) })} openDelay={400}>
            <UnstyledButton role="tab" aria-selected={row.id === picked} className={row.id === picked ? 'on' : undefined}
              aria-label={t('blockRows.pick', { name: name(k) })} onClick={() => onPick(row.id)}>{name(k)}</UnstyledButton>
          </Tooltip>
        ))}
        <Tooltip label={t('blockRows.add')}>
          <ActionIcon variant="default" className="fb-row-tabs-add" aria-label={t('blockRows.add')} disabled={rows.length >= MAX_ROWS}
            onClick={() => { const row = newRow(rows); onSave([...rows, row]); onPick(row.id) }}><IconPlus size={14} /></ActionIcon>
        </Tooltip>
      </div>
      {r && (
        <Group gap="xs" wrap="nowrap" mt="xs">
          {i > 0 ? (
            <>
              <Text size="xs" c="dimmed" style={{ flex: 1 }}>{t('blockRows.gapAbove', { name: name(i) })}</Text>
              <NumberInput key={`${r.id}-${r.gap}`} size="xs" w={96} min={0} max={20} step={0.5} decimalScale={2} aria-label={t('blockRows.gapAboveLabel', { name: name(i) })}
                defaultValue={r.gap} suffix={` ${t('blockRows.seatsUnit')}`}
                onBlur={(e) => {
                  const v = Number(e.currentTarget.value.replace(/[^\d.]/g, ''))
                  if (Number.isFinite(v) && v !== r.gap) onSave(rows.map((x, k) => (k === i ? { ...x, gap: Math.min(20, Math.max(0, v)) } : x)))
                }} />
            </>
          ) : <span style={{ flex: 1 }} />}
          {/* Rows run top to bottom in the block; the tabs read left to right, so earlier is left. */}
          <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === 0} aria-label={t('blockRows.up', { name: name(i) })}
            onClick={() => onSave(moveRow(rows, i, i - 1))}><IconChevronLeft size={14} /></ActionIcon>
          <ActionIcon size="sm" variant="subtle" color="gray" disabled={i === rows.length - 1} aria-label={t('blockRows.down', { name: name(i) })}
            onClick={() => onSave(moveRow(rows, i, i + 1))}><IconChevronRight size={14} /></ActionIcon>
          <ActionIcon size="sm" variant="subtle" color="gray" disabled={rows.length === 1} aria-label={t('blockRows.remove', { name: name(i) })}
            onClick={() => { onSave(rows.filter((_, k) => k !== i)); onPick(rows[i === 0 ? 1 : i - 1]?.id ?? null) }}><IconX size={14} /></ActionIcon>
        </Group>
      )}
    </div>
  )
}
