import { Badge, Button, Group, Paper, Progress, ScrollArea, SegmentedControl, Stack, Text, TextInput, UnstyledButton } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { KeptWalk, WalkRow } from '@/api/seatWalk'
import { rowTitle } from './rowTitle'
import './HallRows.css'

type Filter = 'all' | 'open' | 'mine'

/** The hall beside the walk (D1, issue #1356): who walks now (with Take over), then every row with
 *  how many seats have their port, searchable, so a hall of 30 rows stays one short list. */
export function HallRows({ rows, walks, me, mine, selected, onSelect, onTake }: {
  rows: WalkRow[]; walks: KeptWalk[]; me?: string; mine?: string | null
  selected?: string | null; onSelect?: (id: string) => void; onTake?: (walk: KeptWalk) => void
}) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const myRows = useMemo(() => new Set(walks.filter((w) => w.user === me).flatMap((w) => w.rows)), [walks, me])
  const names = useMemo(() => new Map(rows.map((r) => [r.id, rowTitle(t, r)])), [rows, t])
  const shown = rows.filter((r) => {
    if (filter === 'open' && r.seats > 0 && r.found >= r.seats) return false
    if (filter === 'mine' && !myRows.has(r.id)) return false
    const q = query.trim().toLowerCase()
    return !q || (names.get(r.id) ?? '').toLowerCase().includes(q) || r.name.toLowerCase() === q
  })
  const open = rows.filter((r) => !(r.seats > 0 && r.found >= r.seats)).length
  const seats = rows.reduce((n, r) => n + r.seats, 0)
  const found = rows.reduce((n, r) => n + r.found, 0)
  // Walking now, then walks that stopped: someone else's can be taken over where it got to.
  const people = walks.filter((w) => w.active || w.user !== me)
  const walking = new Set(walks.filter((w) => w.active).map((w) => w.who)).size
  if (!rows.length) return null
  return (
    <Paper withBorder radius="lg" p="md" className="walk-rail">
      <Stack gap="sm">
        <Group justify="space-between" align="baseline" wrap="nowrap">
          <Text fw={600}>{t('seatWalk.hallTitle')}</Text>
          <Text size="sm" c="dimmed">{t('seatWalk.walkersNow', { count: walking })}</Text>
        </Group>
        <TextInput size="sm" leftSection={<IconSearch size={14} />} placeholder={t('seatWalkRows.search')}
          aria-label={t('seatWalkRows.search')} value={query} onChange={(e) => setQuery(e.currentTarget.value)} />
        <SegmentedControl size="xs" fullWidth value={filter} onChange={(v) => setFilter(v as Filter)} data={[
          { value: 'all', label: t('seatWalkRows.all', { count: rows.length }) },
          { value: 'open', label: t('seatWalkRows.open', { count: open }) },
          { value: 'mine', label: t('seatWalkRows.mine', { count: myRows.size }) },
        ]} />
        <Text size="xs" c="dimmed">{t('seatWalkRows.summary', { rows: rows.length, found, seats })}</Text>

        {people.length > 0 && (
          <Stack gap={4}>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{t('seatWalkRows.walkingNow')}</Text>
            {people.map((w) => {
              const own = w.id === mine || (w.user === me && w.active)
              const where = w.rows.map((r) => names.get(r) ?? r).join(', ')
              return (
                <Group key={w.id} gap="xs" wrap="nowrap" className="walk-rail-walker" data-active={w.active || undefined}>
                  <Text size="sm" fw={600} c={own ? 'trace' : w.active ? 'warn' : 'dimmed'} style={{ whiteSpace: 'nowrap' }}>
                    {own ? t('seatWalk.you') : w.who}</Text>
                  <Text size="xs" c="dimmed" truncate style={{ flex: 1 }}>
                    {w.seat ? `${where} · ${w.seat}` : where}
                    {!w.active && ` · ${t('seatWalkRows.stopped')}`}
                  </Text>
                  {!own && onTake && (
                    <Button size="compact-xs" variant="default" onClick={() => onTake(w)}
                      aria-label={t('seatWalkRows.takeOverWho', { who: w.who })}>{t('seatWalkRows.takeOver')}</Button>
                  )}
                </Group>
              )
            })}
          </Stack>
        )}

        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{t('seatWalkRows.rows')}</Text>
        <ScrollArea.Autosize mah="60vh" type="auto" scrollbars="y" offsetScrollbars="y">
          <Stack gap={2} role="list" aria-label={t('seatWalkRows.rows')}>
            {!shown.length && <Text size="sm" c="dimmed">{t('seatWalkRows.none')}</Text>}
            {shown.map((r) => {
              const done = r.seats > 0 && r.found >= r.seats
              const own = !!mine && r.walker?.id === mine
              return (
                <UnstyledButton key={r.id} role="listitem" className="walk-rail-row" data-selected={r.id === selected || undefined}
                  onClick={() => onSelect?.(r.id)} aria-current={r.id === selected ? 'true' : undefined}>
                  <Group justify="space-between" wrap="nowrap" gap="xs">
                    <Text size="sm" fw={600} truncate>{names.get(r.id)}</Text>
                    <Text size="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{t('seatWalk.rowFound', { found: r.found, seats: r.seats })}</Text>
                  </Group>
                  {(r.walker || done || !!r.failed || !!r.marked) && (
                    <Group gap={4} mt={2}>
                      {r.walker ? (
                        <Badge size="sm" variant="light" color={own ? 'up' : 'info'} tt="none">
                          {own ? t('seatWalk.you') : r.walker.who}{r.walker.seat ? ` · ${r.walker.seat}` : ''}</Badge>
                      ) : done ? <Badge size="sm" variant="light" color="up" tt="none">{t('seatWalk.rowDone')}</Badge> : null}
                      {!!r.failed && <Badge size="sm" variant="light" color="down" tt="none">{t('seatWalkRows.failedCount', { count: r.failed })}</Badge>}
                      {!!r.marked && <Badge size="sm" variant="light" color="warn" tt="none">{t('seatWalkRows.markedCount', { count: r.marked })}</Badge>}
                    </Group>
                  )}
                  <Progress value={r.seats ? (100 * r.found) / r.seats : 0} color={done ? 'up' : 'info'} size="sm" mt={4}
                    aria-label={t('seatWalk.rowFound', { found: r.found, seats: r.seats })} />
                </UnstyledButton>
              )
            })}
          </Stack>
        </ScrollArea.Autosize>
      </Stack>
    </Paper>
  )
}
