import { Anchor, Badge, Group, Progress, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { Circuit } from '@/api/types'
import { DataTable } from '@bitsandbricks/ui'
import { ago } from '@/lib/time'
import { feedsText } from './feeds'
import { circuitPath, TONE } from './state'


/** How loaded a circuit is, or that it tripped, and where the number comes from. */
export function Load({ c }: { c: Circuit }) {
  const { t } = useTranslation()
  if (c.state === 'tripped') {
    return <Text size="sm" c="var(--bnb-err)" fw={600}>{t('power.trippedNote', { who: c.tripped?.by ?? '?', ago: ago(c.tripped?.at ?? 0) })}</Text>
  }
  if (!c.reading || c.load_pct === null) return <Text size="sm" c="dimmed">{t('power.state.unknown')}</Text>
  const r = c.reading
  return (
    <Stack gap={2} miw={160}>
      <Progress value={Math.min(100, c.load_pct)} color={TONE[c.state]} size="lg" radius="sm"
        aria-label={t('power.loadOf', { amps: r.amps, rating: c.rating_a, pct: c.load_pct })} />
      <Text size="xs">{t('power.loadOf', { amps: r.amps, rating: c.rating_a, pct: c.load_pct })}</Text>
      <Text size="xs" c="dimmed">
        {r.source === 'plugin' ? t('power.readFrom', { plugin: r.plugin, ago: ago(r.at) }) : t('power.readBy', { who: r.by ?? '?', ago: ago(r.at) })}
      </Text>
    </Stack>
  )
}

/** What a circuit feeds: its rows and switches, and how many seats. */
export function Feeds({ c }: { c: Circuit }) {
  const { t } = useTranslation()
  const parts = [feedsText(t, c), ...c.fed.switches.map((s) => s.name)].filter(Boolean)
  if (!parts.length) return <Text size="sm" c="dimmed">{t('power.nothingFed')}</Text>
  return (
    <Stack gap={0}>
      <Text size="sm">{parts.join(', ')}</Text>
      {c.fed.seats.length > 0 && <Text size="xs" c="dimmed">{t('power.seats', { count: c.fed.seats.length })}</Text>}
    </Stack>
  )
}

export function StateBadge({ c }: { c: Circuit }) {
  const { t } = useTranslation()
  return (
    <Badge size="sm" color={TONE[c.state]} variant={c.state === 'ok' || c.state === 'unknown' ? 'light' : 'filled'}>
      {t(`power.state.${c.state}`)}
    </Badge>
  )
}

/** Circuits as rows that each open the circuit's page: no buttons on the rows (issue #877). */
export function CircuitTable({ circuits }: { circuits: Circuit[] }) {
  const { t } = useTranslation()
  // Several boards each show their circuits on one page, so the view stays out of the address.
  return (
    <DataTable label={t('power.circuits')} rows={circuits} rowKey={(c) => c.id} urlState={false} pageSize={0} bare
      className="fb-table-stack"
      columns={[
        // Fixed shares, so the columns of every board's table line up down the page (issue #1427).
        { id: 'name', header: t('power.circuit'), width: '32%', sort: (c) => c.name, cell: (c) => (
          <div data-circuit={c.id}>
            <Anchor component={Link} to={circuitPath(c.id)} fw={600} size="sm">{c.name}</Anchor>
            <Group gap={4} mt={2}>
              <StateBadge c={c} />
              <Badge size="sm" variant="outline" color="gray">{c.phase} · {c.rating_a} A</Badge>
            </Group>
          </div>
        ) },
        { id: 'load', header: t('power.load'), width: '32%', sort: (c) => c.load_pct ?? -1, cell: (c) => <Load c={c} /> },
        { id: 'feeds', header: t('power.feeds'), wrap: true, cell: (c) => <Feeds c={c} /> },
      ]} />
  )
}
