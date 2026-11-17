import { Alert, Button, Group, Paper, Stack, Table, Text, Title } from '@mantine/core'
import { IconRefresh } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import type { PortClient, PortClients as Clients } from '@/api/types'

const SHOWN = 25

/** Machines on seat ports that the cables don't explain, read from the switches' MAC tables (issue #473). */
export function PortClients({ canEdit, onPatch }: { canEdit: boolean; onPatch: (c: PortClient) => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  // Opening the page asks for a read; the server reads at most every two minutes, in the background.
  const query = useQuery({
    queryKey: qk.portClients, queryFn: () => get<Clients>('/api/cables/clients?read=1'),
    refetchInterval: (q) => (q.state.data?.reading ? 3000 : 60_000),
  })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.portClients })
  useLiveEvent('cables.changed', refresh)
  const infra = useMutation({
    mutationFn: (c: PortClient) => post('/api/cables', { switch: c.switch, port: c.port, note: t('cables.clientsInfraNote') }),
    onSuccess: () => { refresh(); void qc.invalidateQueries({ queryKey: qk.cables }) },
  })
  const c = query.data
  if (!c) return null
  if (!c.as_of && !c.reading && !c.error) return null
  const time = c.as_of ? new Date(c.as_of * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''
  const where = (r: PortClient) => `${r.switch} ${r.port}`
  const who = (r: PortClient) => [r.mac, r.ip].filter(Boolean).join(' · ')
  return (
    <Paper withBorder radius="lg" p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="baseline">
          <Title order={3} size="h4">{t('cables.clientsTitle')}</Title>
          <Group gap="xs">
            <Text size="xs" c="dimmed">
              {c.reading ? t('cables.clientsReading') : t('cables.clientsRead', { time, clients: c.clients, switches: c.switches })}
            </Text>
            <Button size="compact-xs" variant="subtle" leftSection={<IconRefresh size={12} />} disabled={c.reading}
              onClick={refresh}>{t('cables.clientsAgain')}</Button>
          </Group>
        </Group>
        {c.error && <Alert color="down" role="alert">{c.error}</Alert>}
        {c.failed.length > 0 && (
          <Text size="sm" c="warn">{t('cables.clientsFailed', { switches: c.failed.map((f) => f.switch).join(', ') })}</Text>
        )}
        {infra.error && <Alert color="down" role="alert">{infra.error.message}</Alert>}
        {c.as_of && !c.moved.count && !c.unplanned.count && <Text size="sm" c="dimmed">{t('cables.clientsNone')}</Text>}
        {c.moved.count > 0 && (
          <Stack gap={4}>
            <Text size="sm" fw={600}>{t('cables.clientsMoved', { count: c.moved.count })}</Text>
            {c.moved.rows.slice(0, SHOWN).map((r) => (
              <Text key={`${r.switch}-${r.port}-${r.mac}`} size="sm">
                {t('cables.clientsMovedLine', { port: where(r), seat: r.seat, other: r.ip_seat, ip: r.ip })}
              </Text>
            ))}
          </Stack>
        )}
        {c.unplanned.count > 0 && (
          <Stack gap={4}>
            <Text size="sm" fw={600}>{t('cables.clientsUnplanned', { count: c.unplanned.count })}</Text>
            <Table.ScrollContainer minWidth={520}>
              <Table>
                <Table.Tbody>
                  {c.unplanned.rows.slice(0, SHOWN).map((r) => (
                    <Table.Tr key={`${r.switch}-${r.port}-${r.mac}`}>
                      <Table.Td ff="monospace">{where(r)}</Table.Td>
                      <Table.Td ff="monospace">{who(r)}</Table.Td>
                      <Table.Td>{r.ip_seat ? t('cables.clientsIpOf', { seat: r.ip_seat }) : ''}
                        {r.area && <Text size="xs" c="dimmed">{t('cables.areaHint', { label: r.area.label })}</Text>}</Table.Td>
                      {canEdit && (
                        <Table.Td>
                          <Group gap={6} justify="flex-end" wrap="nowrap">
                            <Button size="compact-sm" variant="default" onClick={() => onPatch(r)}>{t('cables.clientsPatch')}</Button>
                            <Button size="compact-sm" variant="subtle" loading={infra.isPending && infra.variables === r}
                              onClick={() => infra.mutate(r)}>{t('cables.clientsInfra')}</Button>
                          </Group>
                        </Table.Td>
                      )}
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            {c.unplanned.count > SHOWN && <Text size="sm" c="dimmed">{t('cables.checkMore', { count: c.unplanned.count - SHOWN })}</Text>}
          </Stack>
        )}
      </Stack>
    </Paper>
  )
}
