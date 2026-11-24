import { Badge, Group, Stack, Table, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { FirewallList } from '@/api/types'
import { ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { RangeForm } from './RangeForm'
import { ROUTE_TONE, useSwitchScope } from './scope'

/** On a firewall range's inventory page: its plan, changed here (#1312), and where each part runs now. */
export function RangePanel({ id, canEdit, prefix, name }: { id: string; canEdit: boolean; prefix?: string; name?: string }) {
  const { t } = useTranslation()
  const q = useQuery({ queryKey: qk.firewalls, queryFn: () => get<FirewallList>('/api/firewalls'), refetchInterval: 15_000 })
  const scope = useSwitchScope()
  if (q.isPending) return <LoadingState />
  if (!q.data) return <ErrorBanner error={q.error} />
  const range = q.data.ranges.find((r) => r.id === id)
  if (!range) {
    // A prefix no firewall routes yet: its plan starts here, on the prefix (IPAM, #1346).
    if (!canEdit || !prefix) return null
    return (
      <Panel title={t('ipam.routeIt')}>
        <Text size="sm" c="dimmed" mb="sm">{t('ipam.noRoute')}</Text>
        <RangeForm range={null} cidr={prefix} name={name} names={q.data.firewalls.map((f) => f.name)} scope={scope} />
      </Panel>
    )
  }
  return (
    <>
      <Panel title={t('firewalls.parts')}>
        <Table verticalSpacing={6} fz="sm">
          <Table.Thead><Table.Tr><Table.Th>{t('firewalls.range')}</Table.Th><Table.Th>{t('firewalls.planned')}</Table.Th>
            <Table.Th>{t('firewalls.now')}</Table.Th><Table.Th ta="right">{t('firewalls.seats')}</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {range.parts.map((p) => (
              <Table.Tr key={p.cidr}>
                <Table.Td ff="monospace">{p.cidr}</Table.Td>
                <Table.Td ff="monospace">{p.firewall}</Table.Td>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <Text size="sm" ff="monospace">{p.now ?? '—'}</Text>
                    <Badge size="sm" color={ROUTE_TONE[p.state]} variant="light">{t(`firewalls.route.${p.state}`)}</Badge>
                  </Group>
                </Table.Td>
                <Table.Td ta="right">{p.seats}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Panel>
      <Panel title={t('firewalls.plan')}>
        {canEdit ? <RangeForm key={JSON.stringify(range)} range={range} names={q.data.firewalls.map((f) => f.name)} scope={scope} />
          : (
            <Stack gap={4}>
              <Text size="sm" ff="monospace">{range.cidr}</Text>
              <Text size="sm">{range.firewalls.join(', ')}</Text>
              {range.fallback.length > 0 && <Text size="xs" c="dimmed">{t('firewalls.fallsBack', { list: range.fallback.join(', ') })}</Text>}
            </Stack>
          )}
      </Panel>
    </>
  )
}
