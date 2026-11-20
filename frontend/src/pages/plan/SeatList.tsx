import { Button, Group, Text, UnstyledButton } from '@mantine/core'
import { IconDownload } from '@tabler/icons-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanSeat, SeatViewData } from '@/api/types'
import { DataTable, type DataColumn } from '@/components/DataTable'
import { type Filter, matches, minutesAgo, rate, seatOrder } from './model'
import { SeatGlyph } from './SeatMap'

const STATE_ORDER = { offline: 0, unknown: 1, online: 2 }
type Row = [string, PlanSeat, number]

/** The hall's seats as a sortable table (issue #169): the plain way through the hall for screen
 *  readers and small phones, with the same filter as the map. */
export function SeatList({ data, filter, selected, onSelect }: {
  data: SeatViewData; filter: Filter; selected: string | null; onSelect: (seat: string) => void
}) {
  const { t } = useTranslation()
  // Rows come in seat order and carry their place in it, so equal values (two idle seats) stay in seat order.
  const rows = useMemo<Row[]>(() => Object.entries(data.seats).filter(([, s]) => matches(s, filter))
    .sort((a, b) => seatOrder(a[0], b[0])).map(([seat, s], i) => [seat, s, i]), [data.seats, filter])

  const columns = useMemo<DataColumn<Row>[]>(() => [
    { id: 'seat', header: t('plan.list.seat'), sort: (r) => r[2],
      cell: ([seat]) => <UnstyledButton onClick={() => onSelect(seat)} fw={700} className="fb-seat-list-seat">{seat}</UnstyledButton> },
    { id: 'state', header: t('plan.list.state'), sort: (r) => STATE_ORDER[r[1].state],
      cell: ([, s]) => (
        <Group gap={6} wrap="nowrap">
          <svg viewBox="-4 -4 40 40" width={18} height={18} aria-hidden="true" className="fb-plan"><SeatGlyph seat={{ state: s.state }} size={32} detail={false} /></svg>
          {t(`plan.state.${s.state}`)}
        </Group>
      ) },
    { id: 'problems', header: t('plan.problems'), numeric: true, descFirst: true, sort: (r) => r[1].problems ?? 0,
      cell: ([, s]) => <Text span inherit c={s.problems ? 'down' : 'dimmed'}>{s.problems ?? 0}</Text> },
    { id: 'bps', header: t('plan.traffic'), numeric: true, descFirst: true, sort: (r) => r[1].bps ?? 0,
      cell: ([, s]) => (s.bps ? rate(s.bps) : '–') },
    { id: 'changed', header: t('plan.list.changed'), descFirst: true, sort: (r) => r[1].changed ?? 0,
      cell: ([, s]) => (s.changed ? t('plan.list.ago', { count: minutesAgo(s.changed) }) : '–') },
    ...(data.checkin ? [{ id: 'checkin', header: t('plan.checkin'), cell: ([, s]: Row) => (s.checked_in ? t('plan.yes') : t('plan.no')) }] : []),
    { id: 'note', header: t('plan.list.note'), descFirst: true, sort: (r) => Number(!!r[1].note),
      cell: ([, s]) => (s.note ? t('plan.yes') : '–') },
  ], [t, onSelect, data.checkin])

  const csv = () => {
    const cell = (v: string | number) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))
    const lines = [['seat', 'state', 'problems', 'bps', ...(data.checkin ? ['checked_in'] : []), 'note']]
    for (const [seat, s] of rows) {
      lines.push([seat, s.state, String(s.problems ?? 0), String(s.bps ?? ''), ...(data.checkin ? [s.checked_in ? 'yes' : 'no'] : []), s.note ? 'yes' : 'no'])
    }
    const url = URL.createObjectURL(new Blob([lines.map((l) => l.map(cell).join(',')).join('\n') + '\n'], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `seats-${data.hall}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fb-seat-list">
      <Group justify="space-between" mb="xs">
        <Text size="sm" c="dimmed" role="status">{t('plan.list.count', { count: rows.length })}</Text>
        <Button size="xs" variant="default" leftSection={<IconDownload size={14} />} onClick={csv} disabled={!rows.length}>CSV</Button>
      </Group>
      <DataTable rows={rows} columns={columns} rowKey={(r) => r[0]} label={t('plan.list.label')} defaultSort={{ id: 'seat' }}
        urlState={false} pageSize={0} bare striped density="compact" minWidth={420}
        rowProps={(r) => (selected === r[0] ? { className: 'sel', 'aria-selected': true } : { 'aria-selected': false })} />
    </div>
  )
}
