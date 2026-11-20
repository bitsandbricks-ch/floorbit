import { Badge, Group, Paper, Progress, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { WalkHallRow } from '@/api/types'

function rowTitle(t: (k: string, o?: Record<string, unknown>) => string, r: Pick<WalkHallRow, 'name' | 'block_label' | 'naming'>) {
  return r.naming === 'rows' ? t('seatWalk.rowName', { name: r.name }) : t('seatWalk.blockRow', { block: r.block_label, name: r.name })
}

/** The hall at a glance (#1000): every row, how many seats have their port, and who walks it now,
 *  so several walkers split the hall without asking around. ``mine``: this walker's own walk. */
export function HallRows({ rows, mine, onPick }: { rows: WalkHallRow[]; mine?: string | null; onPick?: (id: string) => void }) {
  const { t } = useTranslation()
  if (!rows.length) return null
  const walking = new Set(rows.filter((r) => r.walker).map((r) => r.walker!.who)).size
  return (
    <Paper withBorder radius="lg" p="lg">
      <Stack gap="sm">
        <Group justify="space-between" align="baseline">
          <Title order={2} size="h4">{t('seatWalk.hallTitle')}</Title>
          <Text size="sm" c="dimmed">{t('seatWalk.walkersNow', { count: walking })}</Text>
        </Group>
        {rows.map((r) => {
          const done = r.seats > 0 && r.found >= r.seats
          const own = !!mine && r.walker?.id === mine
          return (
            <Stack key={r.id} gap={2}>
              <Group justify="space-between" wrap="nowrap" gap="xs">
                <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                  <Text size="sm" fw={600} truncate
                    style={onPick && !r.walker ? { cursor: 'pointer' } : undefined}
                    onClick={onPick && !r.walker ? () => onPick(r.id) : undefined}>{rowTitle(t, r)}</Text>
                  {r.walker ? (
                    <Badge variant="light" color={own ? 'up' : 'info'} tt="none">
                      {own ? t('seatWalk.you') : r.walker.who}{r.walker.seat ? ` · ${r.walker.seat}` : ''}</Badge>
                  ) : done ? <Badge variant="light" color="up" tt="none">{t('seatWalk.rowDone')}</Badge> : null}
                </Group>
                <Text size="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{t('seatWalk.rowFound', { found: r.found, seats: r.seats })}</Text>
              </Group>
              <Progress value={r.seats ? (100 * r.found) / r.seats : 0} color={done ? 'up' : 'info'} size="sm"
                aria-label={t('seatWalk.rowFound', { found: r.found, seats: r.seats })} />
            </Stack>
          )
        })}
      </Stack>
    </Paper>
  )
}
