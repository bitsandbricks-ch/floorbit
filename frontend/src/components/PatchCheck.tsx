import { Alert, Group, Paper, Progress, Stack, Text, Title } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { PatchCheck as Check, PatchRow } from '@/api/types'
import { clock } from '@/lib/time'

function Rows({ rows, count, line }: { rows: PatchRow[]; count: number; line: (r: PatchRow) => string }) {
  const { t } = useTranslation()
  return (
    <Stack gap={0}>
      {rows.slice(0, 8).map((r) => <Text key={`${r.switch}-${r.port}`} size="sm" ff="monospace">{line(r)}</Text>)}
      {count > 8 && <Text size="sm" c="dimmed">{t('cables.checkMore', { count: count - 8 })}</Text>}
    </Stack>
  )
}

/** The patch plan against the port watch's last read (issue #473): seat ports up, typos, surprises. */
export function PatchCheck() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.cableCheck, queryFn: () => get<Check>('/api/cables/check') })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.cableCheck })
  useLiveEvent('attention.changed', refresh)
  useLiveEvent('cables.changed', refresh)
  const c = query.data
  if (!c || (!c.blocks.length && !c.unplanned.count)) return null
  const port = (r: PatchRow) => `${r.switch} ${r.port}`
  return (
    <Paper withBorder radius="lg" p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="baseline">
          <Title order={3} size="h4">{t('cables.checkTitle')}</Title>
          {c.last_poll && <Text size="xs" c="dimmed">
            {t('cables.checkRead', { time: clock(c.last_poll) })}
          </Text>}
        </Group>
        {c.blocks.map((b) => (
          <Stack key={b.block || 'none'} gap={2}>
            <Group justify="space-between">
              <Text size="sm" fw={600}>{b.block ? t('cables.checkBlock', { name: b.name || '–' }) : t('cables.checkLoose')}</Text>
              <Text size="sm">{t('cables.checkUp', { up: b.up, seats: b.seats })}</Text>
            </Group>
            <Progress value={b.seats ? (100 * b.up) / b.seats : 0} color="up" size="sm"
              aria-label={t('cables.checkUp', { up: b.up, seats: b.seats })} />
          </Stack>
        ))}
        {c.missing.count > 0 && (
          <Alert color="down" title={t('cables.checkMissing', { count: c.missing.count })}>
            <Rows rows={c.missing.rows} count={c.missing.count} line={(r) => `${r.seat}: ${port(r)}`} />
          </Alert>
        )}
        {c.conflicts.count > 0 && (
          <Alert color="warn" title={t('cables.checkConflicts', { count: c.conflicts.count })}>
            <Rows rows={c.conflicts.rows} count={c.conflicts.count}
              line={(r) => t('cables.checkConflict', { port: port(r), seat: r.seat, described: r.described_seat })} />
          </Alert>
        )}
        {c.unplanned.count > 0 && (
          <Alert color="info" title={t('cables.checkUnplanned', { count: c.unplanned.count })}>
            <Rows rows={c.unplanned.rows} count={c.unplanned.count} line={port} />
          </Alert>
        )}
        {c.down.count > 0 && (
          <Text size="sm" c="dimmed">{t('cables.checkDown', { count: c.down.count, seats: c.down.rows.slice(0, 6).map((r) => r.seat).join(', ') })}</Text>
        )}
        {c.unread.length > 0 && <Text size="sm" c="dimmed">{t('cables.checkUnread', { switches: c.unread.join(', ') })}</Text>}
      </Stack>
    </Paper>
  )
}
