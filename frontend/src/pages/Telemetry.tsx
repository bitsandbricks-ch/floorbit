import { Alert, Badge, Button, Code, Group, Modal, Paper, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { ConfirmButton } from '@/components/ConfirmButton'
import type { EntityOption } from '@/components/EntitySelect'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { DeviceProblems, DeviceTelemetryActions } from '@/components/telemetry/DeviceTelemetry'
import type { DeviceSeen } from '@/components/telemetry/api'
import { TelemetryAgentNumbersList, type TelemetryAgentNumbers } from '@/components/telemetry/AgentNumbers'
import { ago, dateTime } from '@/lib/time'

/** A device telemetry collects from: an inventory device with the Telemetry feature on. No logins. */
export interface TelemetryDevice {
  id: string; name: string; address: string; kind: string; platform: string; drivers: string[]
  agent: string; inventory_id: string; ports: { snmp?: number; gnmi?: number; api?: number }
}
/** GET /api/telemetry/overview (floorbit/blueprints/telemetry.py). */
export interface TelemetryOverview {
  devices: TelemetryDevice[]; seen: Record<string, DeviceSeen>
  status: { collector: 'here' | 'agent'; devices: number; points: number | null; unknown: number; poll_errors: Record<string, string>
    agents?: TelemetryAgentNumbers[]
    storage: { mode: string; keep_days: number | null; errors: Record<string, string> } }
}

const KEY = ['telemetry-overview'] as const

/** Monitoring > Telemetry: what the collector hears from each device (docs/telemetry.md). Devices
 *  are set up in the inventory: the Telemetry feature, logins and properties on a device or group. */
export default function Telemetry() {
  const { t } = useTranslation()
  const isAdmin = useCan('settings.manage')
  const data = useQuery({ queryKey: KEY, queryFn: () => get<TelemetryOverview>('/api/telemetry/overview'), refetchInterval: 15_000 })
  // The same cached list the inventory's agent field shows: an agent by its name.
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') })
  const agentName = (id: string) => agents.data?.options.find((o) => o.value === id)?.label ?? id
  const [paste, setPaste] = useState<{ name: string; config: string } | null>(null)
  const config = useMutation({
    mutationFn: (name: string) => get<{ config: string }>(`/api/telemetry/device-config?name=${encodeURIComponent(name)}`)
      .then((r) => ({ name, config: r.config })),
    onSuccess: setPaste,
  })
  const d = data.data
  const label = (ns: string, v: string) => t(`telemetry.${ns}.${v}`, { defaultValue: v })

  return (
    <Layout title={t('telemetry.title')}>
      <PageHead title={t('telemetry.title')} desc={t('telemetry.intro')}
        actions={<Button component={Link} to="/inventory" variant="default">{t('telemetry.openInventory')}</Button>} />
      <Stack gap="md">
        {data.error && <Alert color="down" role="alert">{data.error.message}</Alert>}
        {d && (
          <Paper withBorder radius="lg" p="md">
            <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
              <Stat label={t('telemetry.collector')} value={t(`telemetry.collectorIs.${d.status.collector}`)} />
              <Stat label={t('telemetry.storage')} value={t(`telemetry.storageIs.${d.status.storage.mode}`, { days: d.status.storage.keep_days })} />
              <Stat label={t('telemetry.devices')} value={String(d.status.devices)} />
              {d.status.points !== null && <Stat label={t('telemetry.points')} value={String(d.status.points)} />}
            </SimpleGrid>
            {d.status.agents && d.status.agents.length > 0 && <Stack mt="sm"><TelemetryAgentNumbersList agents={d.status.agents} /></Stack>}
            {Object.entries({ ...d.status.poll_errors, ...d.status.storage.errors }).map(([what, msg]) => (
              <Alert key={what} mt="sm" color="warn" title={what}>{msg}</Alert>
            ))}
          </Paper>
        )}

        <Paper withBorder radius="lg" p="md">
          <Title order={3} size="h4" mb="xs">{t('telemetry.devicesTitle')}</Title>
          {d && !d.devices.length ? <Text size="sm" c="dimmed">{t('telemetry.empty')}</Text> : (
            <Table.ScrollContainer minWidth={560}>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('telemetry.device')}</Table.Th><Table.Th>{t('telemetry.drivers')}</Table.Th>
                    <Table.Th visibleFrom="sm">{t('telemetry.agent')}</Table.Th><Table.Th>{t('telemetry.lastSeen')}</Table.Th>
                    <Table.Th visibleFrom="sm">{t('telemetry.what')}</Table.Th>{isAdmin && <Table.Th />}
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {d?.devices.map((dev) => {
                    const s = d.seen[dev.name]
                    return (
                      <Table.Tr key={dev.id}>
                        <Table.Td>
                          <Text ff="monospace" size="sm">{dev.name}</Text>
                          <Text size="xs" c="dimmed">{dev.address} · {label('platform', dev.platform)}</Text>
                          <DeviceProblems problems={s?.problems} />
                        </Table.Td>
                        <Table.Td><Group gap={4}>{dev.drivers.map((x) => <Badge key={x} variant="light" size="sm" tt="none">{label('driver', x)}</Badge>)}</Group></Table.Td>
                        <Table.Td visibleFrom="sm"><Text size="sm" c={dev.agent ? undefined : 'dimmed'}>{dev.agent ? agentName(dev.agent) : t('telemetry.anyAgent')}</Text></Table.Td>
                        <Table.Td>
                          {s?.seen ? <Badge color={s.online ? 'up' : 'down'} variant="light" tt="none" miw="max-content" title={dateTime(s.seen)}>{ago(s.seen)}</Badge>
                            : <Text size="sm" c="dimmed">{t('telemetry.never')}</Text>}
                        </Table.Td>
                        <Table.Td visibleFrom="sm"><Text size="sm">{s?.ports !== undefined ? t('telemetry.counts', { ...s }) : '–'}</Text></Table.Td>
                        {isAdmin && (
                          <Table.Td>
                            <Group gap={6} justify="flex-end" wrap="nowrap">
                              {d.status.collector === 'agent' && <DeviceTelemetryActions name={dev.name} />}
                              <Button size="compact-sm" variant="default" loading={config.isPending && config.variables === dev.name}
                                onClick={() => config.mutate(dev.name)}>{t('telemetry.deviceConfig')}</Button>
                            </Group>
                          </Table.Td>
                        )}
                      </Table.Tr>
                    )
                  })}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
          {config.error && <Alert mt="sm" color="down" role="alert">{config.error.message}</Alert>}
        </Paper>

        {isAdmin && <Senders collector={d?.status.collector} />}
      </Stack>
      <Modal opened={!!paste} onClose={() => setPaste(null)} title={t('telemetry.pasteTitle', { name: paste?.name })} size="lg">
        <Stack gap="sm">
          <Text size="sm">{t('telemetry.pasteIntro')}</Text>
          {paste?.config ? <Code block>{paste.config}</Code> : <Text c="dimmed">{t('telemetry.pasteNothing')}</Text>}
        </Stack>
      </Modal>
    </Layout>
  )
}

/** The ingest token senders use, and the sidecar's config while no agent collects. */
function Senders({ collector }: { collector?: 'here' | 'agent' }) {
  const { t } = useTranslation()
  const [token, setToken] = useState<string | null>(null)
  const reveal = useMutation({ mutationFn: () => get<{ token: string }>('/api/telemetry/token'), onSuccess: (r) => setToken(r.token) })
  const renew = useMutation({ mutationFn: () => post<{ token: string }>('/api/telemetry/token'), onSuccess: (r) => setToken(r.token) })
  const error = reveal.error || renew.error
  return (
    <Paper withBorder radius="lg" p="md">
      <Stack gap="sm">
        <Title order={3} size="h4">{t('telemetry.sendersTitle')}</Title>
        <Text size="sm">{t('telemetry.senders')}</Text>
        <Group gap="sm">
          {token ? <Code>{token}</Code> : <Button variant="default" loading={reveal.isPending} onClick={() => reveal.mutate()}>{t('telemetry.showToken')}</Button>}
          <ConfirmButton variant="subtle" danger label={t('telemetry.newToken')} question={t('telemetry.newTokenQuestion')}
            onConfirm={() => renew.mutate()} />
          {collector === 'here' && (
            <Button component="a" variant="default" href="/api/telemetry/telegraf.conf">{t('telemetry.download')}</Button>
          )}
        </Group>
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
      </Stack>
    </Paper>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={0}>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={600}>{value}</Text>
    </Stack>
  )
}
