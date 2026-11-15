import { Button, Group, Table, Text, UnstyledButton } from '@mantine/core'
import { IconChevronDown, IconChevronUp, IconDownload } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanSeat, SeatViewData } from '@/api/types'
import { type Filter, matches, minutesAgo, rate, seatOrder } from './model'
import { SeatGlyph } from './SeatMap'

type Key = 'seat' | 'state' | 'problems' | 'bps' | 'changed'
const STATE_ORDER = { offline: 0, unknown: 1, online: 2 }

/** The hall's seats as a sortable table (issue #169): the plain way through the hall for screen
 *  readers and small phones, with the same filter as the map. */
export function SeatList({ data, filter, selected, onSelect }: {
  data: SeatViewData; filter: Filter; selected: string | null; onSelect: (seat: string) => void
}) {
  const { t } = useTranslation()
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: 'seat', desc: false })
  const rows = useMemo(() => {
    const list = Object.entries(data.seats).filter(([, s]) => matches(s, filter))
    const by: Record<Key, (a: [string, PlanSeat], b: [string, PlanSeat]) => number> = {
      seat: (a, b) => seatOrder(a[0], b[0]),
      state: (a, b) => STATE_ORDER[a[1].state] - STATE_ORDER[b[1].state] || seatOrder(a[0], b[0]),
      problems: (a, b) => (a[1].problems ?? 0) - (b[1].problems ?? 0) || seatOrder(b[0], a[0]),
      bps: (a, b) => (a[1].bps ?? 0) - (b[1].bps ?? 0) || seatOrder(b[0], a[0]),
      changed: (a, b) => (a[1].changed ?? 0) - (b[1].changed ?? 0) || seatOrder(b[0], a[0]),
    }
    list.sort(by[sort.key])
    return sort.desc ? list.reverse() : list
  }, [data.seats, filter, sort])

  const head = (key: Key, label: string, numeric = false) => {
    const on = sort.key === key
    // Problems, traffic and changes start with the most (or latest), seats and states with the first.
    const flip = () => setSort(on ? { key, desc: !sort.desc } : { key, desc: key === 'problems' || key === 'bps' || key === 'changed' })
    return (
      <Table.Th aria-sort={on ? (sort.desc ? 'descending' : 'ascending') : 'none'} ta={numeric ? 'right' : undefined}>
        <UnstyledButton onClick={flip} fw={600} fz="sm">
          <Group gap={4} wrap="nowrap" justify={numeric ? 'flex-end' : undefined}>
            {label}
            {on && (sort.desc ? <IconChevronDown size={14} aria-hidden /> : <IconChevronUp size={14} aria-hidden />)}
          </Group>
        </UnstyledButton>
      </Table.Th>
    )
  }

  const csv = () => {
    const cell = (v: string | number) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))
    const lines = [['seat', 'state', 'problems', 'bps', ...(data.checkin ? ['checked_in'] : []), 'match']]
    for (const [seat, s] of rows) {
      lines.push([seat, s.state, String(s.problems ?? 0), String(s.bps ?? ''), ...(data.checkin ? [s.checked_in ? 'yes' : 'no'] : []), s.match ?? ''])
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
      <Table.ScrollContainer minWidth={420}>
        <Table striped highlightOnHover verticalSpacing={4} aria-label={t('plan.list.label')}>
          <Table.Thead>
            <Table.Tr>
              {head('seat', t('plan.list.seat'))}
              {head('state', t('plan.list.state'))}
              {head('problems', t('plan.problems'), true)}
              {head('bps', t('plan.traffic'), true)}
              {head('changed', t('plan.list.changed'))}
              {data.checkin && <Table.Th>{t('plan.checkin')}</Table.Th>}
              <Table.Th>{t('plan.list.match')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map(([seat, s]) => (
              <Table.Tr key={seat} className={selected === seat ? 'sel' : undefined} aria-selected={selected === seat}>
                <Table.Td>
                  <UnstyledButton onClick={() => onSelect(seat)} fw={700} className="fb-seat-list-seat">{seat}</UnstyledButton>
                </Table.Td>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <svg viewBox="-4 -4 40 40" width={18} height={18} aria-hidden="true" className="fb-plan"><SeatGlyph seat={{ state: s.state }} size={32} detail={false} /></svg>
                    {t(`plan.state.${s.state}`)}
                  </Group>
                </Table.Td>
                <Table.Td ta="right" c={s.problems ? 'down' : 'dimmed'}>{s.problems ?? 0}</Table.Td>
                <Table.Td ta="right">{s.bps ? rate(s.bps) : '–'}</Table.Td>
                <Table.Td>{s.changed ? t('plan.list.ago', { count: minutesAgo(s.changed) }) : '–'}</Table.Td>
                {data.checkin && <Table.Td>{s.checked_in ? t('plan.yes') : t('plan.no')}</Table.Td>}
                <Table.Td>{s.match ?? '–'}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </div>
  )
}
