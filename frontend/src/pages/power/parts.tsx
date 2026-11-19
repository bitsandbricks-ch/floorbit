import { Anchor, Badge, Group, Progress, Stack, Table, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { Circuit } from '@/api/types'
import { ago } from '@/lib/time'
import { circuitPath, TONE } from './state'


/** How loaded a circuit is, or that it tripped, and where the number comes from. */
export function Load({ c }: { c: Circuit }) {
  const { t } = useTranslation()
  if (c.state === 'tripped') {
    return <Text size="sm" c="var(--color-down)" fw={600}>{t('power.trippedNote', { who: c.tripped?.by ?? '?', ago: ago(c.tripped?.at ?? 0) })}</Text>
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
  const parts = [c.feeds_label, ...c.fed.switches.map((s) => s.name)].filter(Boolean)
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
  return (
    <Table verticalSpacing="xs" className="fb-table-stack">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>{t('power.circuit')}</Table.Th>
          <Table.Th>{t('power.load')}</Table.Th>
          <Table.Th>{t('power.feeds')}</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {circuits.map((c) => (
          <Table.Tr key={c.id} data-circuit={c.id}>
            <Table.Td>
              <Anchor component={Link} to={circuitPath(c.id)} fw={600} size="sm">{c.name}</Anchor>
              <Group gap={4} mt={2}>
                <StateBadge c={c} />
                <Badge size="sm" variant="outline" color="gray">{c.phase} · {c.rating_a} A</Badge>
              </Group>
            </Table.Td>
            <Table.Td><Load c={c} /></Table.Td>
            <Table.Td><Feeds c={c} /></Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}
