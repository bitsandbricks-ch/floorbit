import { ActionIcon, Group, NumberInput, Tabs, Text, Tooltip } from '@mantine/core'
import { IconPlus, IconX } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PIECES_MAX, addPiece, dropPiece, piecesOf, withPieceSeats } from './pieces'
import type { BlockRow } from './rows'

/** A path row's pieces as tabs (Mike's row Z: a U with a line of seats inside it, one row with one
 *  run of names). The seats run through the pieces in order; the first takes what the others leave. */
export function PieceFields({ row, onSave }: { row: BlockRow; onSave: (row: BlockRow) => void }) {
  const { t } = useTranslation()
  const pieces = piecesOf(row)
  const [open, setOpen] = useState(0)
  const k = Math.min(open, pieces.length - 1)
  const first = pieces.slice(0, k).reduce((a, p) => a + p.seats, 0) + 1
  const last = first + pieces[k].seats - 1
  return (
    <div>
      <Group gap={4} wrap="nowrap" align="flex-end">
        <Tabs value={String(k)} onChange={(v) => v && setOpen(Number(v))} style={{ flex: 1, minWidth: 0 }}>
          <Tabs.List>
            {pieces.map((_, i) => <Tabs.Tab key={i} value={String(i)} px="sm">{t('blockRows.piece', { n: i + 1 })}</Tabs.Tab>)}
          </Tabs.List>
        </Tabs>
        <Tooltip label={t('blockRows.addPiece')}>
          <ActionIcon variant="subtle" aria-label={t('blockRows.addPiece')} disabled={pieces.length >= PIECES_MAX || pieces[0].seats < 2}
            onClick={() => { const next = addPiece(row); if (next !== row) { onSave(next); setOpen(pieces.length) } }}><IconPlus size={16} /></ActionIcon>
        </Tooltip>
      </Group>
      <Group gap="xs" wrap="nowrap" mt="xs" align="flex-end">
        {k === 0 ? (
          <Text size="sm" style={{ flex: 1 }}>{t('blockRows.pieceFirst', { from: first, to: last, count: pieces[0].seats })}</Text>
        ) : (
          <>
            <NumberInput key={`${k}-${pieces[k].seats}`} size="xs" style={{ flex: 1 }} label={t('blockRows.pieceSeats', { n: k + 1 })}
              description={t('blockRows.pieceRange', { from: first, to: last })} min={1} max={row.seats - 1} defaultValue={pieces[k].seats}
              onBlur={(e) => { const v = Number(e.currentTarget.value); if (Number.isFinite(v) && v !== pieces[k].seats) onSave(withPieceSeats(row, k, v)) }}
              onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }} />
            <Tooltip label={t('blockRows.dropPiece', { n: k + 1 })}>
              <ActionIcon variant="subtle" color="gray" mb={4} aria-label={t('blockRows.dropPiece', { n: k + 1 })}
                onClick={() => { onSave(dropPiece(row, k)); setOpen(k - 1) }}><IconX size={14} /></ActionIcon>
            </Tooltip>
          </>
        )}
      </Group>
      <Text size="xs" c="dimmed" mt={4}>{t(pieces.length > 1 ? 'blockRows.piecesHint' : 'blockRows.pathHint')}</Text>
    </div>
  )
}
