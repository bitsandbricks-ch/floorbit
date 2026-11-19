import { ActionIcon, Alert, Badge, Button, Code, Group, SegmentedControl, SimpleGrid, Stack, Table, Text, TextInput, Tooltip } from '@mantine/core'
import { IconPencil, IconSearch } from '@tabler/icons-react'
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
import { PageTabs } from '@/components/PageTabs'
import { usePageTab } from '@/components/pageTab'
import { StatCard } from '@/components/StatCard'
import { DeviceProblems, DeviceTelemetryActions } from '@/components/telemetry/DeviceTelemetry'
import type { DeviceSeen } from '@/components/telemetry/api'
import { TelemetryAgentNumbersList, type TelemetryAgentNumbers } from '@/components/telemetry/AgentNumbers'
import { EmptyState, Field, Panel } from '@/components/ui'
import { ago, dateTime } from '@/lib/time'
import { telemetryPath } from './inventory/model'

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
type Show = 'all' | 'problems' | 'silent'

/** Monitoring > Telemetry: what the collector hears from each device (docs/telemetry.md). Each
 *  device opens its own page (the inventory's Telemetry tab), where it is set up and tested. */
export default function Telemetry() {
  const { t } = useTranslation()
  const isAdmin = useCan('settings.manage')
  const data = useQuery({ queryKey: KEY, queryFn: () => get<TelemetryOverview>('/api/telemetry/overview'), refetchInterval: 15_000 })
  const d = data.data
  const [tab, setTab] = usePageTab(['devices', 'collector', ...(isAdmin ? ['senders'] : [])])
  const problems = d ? d.devices.filter((x) => d.seen[x.name]?.problems?.length).length : 0
  const silent = d ? d.devices.filter((x) => !d.seen[x.name]?.seen).length : 0
  const errors = d ? Object.keys({ ...d.status.poll_errors, ...d.status.storage.errors }).length : 0

  return (
    <Layout title={t('telemetry.title')}>
      <PageHead title={t('telemetry.title')} desc={t('telemetry.intro')}
        actions={<Button component={Link} to="/inventory" variant="default">{t('telemetry.openInventory')}</Button>} />
      <Stack gap="md">
        {data.error && <Alert color="down" role="alert">{data.error.message}</Alert>}
        {d && (
          <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm" aria-label={t('telemetry.summary')}>
            <StatCard label={t('telemetry.devicesTitle')} value={String(d.devices.length)}
              sub={t(`telemetry.collectorIs.${d.status.collector}`)} />
            <StatCard label={t('telemetry.heardCard')} value={`${d.devices.length - silent} / ${d.devices.length}`}
              tone={!d.devices.length ? undefined : silent ? (silent === d.devices.length ? 'down' : 'warn') : 'up'} />
            <StatCard label={t('telemetry.problemsCard')} value={String(problems)} tone={problems ? 'warn' : undefined}
              sub={problems ? undefined : t('telemetry.noProblems')} />
            <StatCard label={t('telemetry.points')} value={d.status.points !== null ? String(d.status.points) : '–'}
              tone={Object.keys(d.status.storage.errors).length ? 'down' : undefined}
              sub={t(`telemetry.storageIs.${d.status.storage.mode}`, { days: d.status.storage.keep_days })} />
          </SimpleGrid>
        )}
        <PageTabs label={t('telemetry.title')} value={tab} onChange={setTab} tabs={[
          { id: 'devices', label: t('telemetry.devicesTitle'), count: d?.devices.length },
          { id: 'collector', label: t('telemetry.collectorTab'), alert: errors ? 'warn' : null },
          ...(isAdmin ? [{ id: 'senders', label: t('telemetry.sendersTitle') }] : []),
        ]} />
        {tab === 'devices' && <Devices d={d} isAdmin={isAdmin} />}
        {tab === 'collector' && d && <Collector d={d} />}
        {tab === 'senders' && isAdmin && <Senders collector={d?.status.collector} />}
      </Stack>
    </Layout>
  )
}

function Devices({ d, isAdmin }: { d?: TelemetryOverview; isAdmin: boolean }) {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  // The same cached list the inventory's agent field shows: an agent by its name.
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') })
  const agentName = (id: string) => agents.data?.options.find((o) => o.value === id)?.label ?? id
  const [q, setQ] = useState('')
  const [show, setShow] = useState<Show>('all')
  const label = (ns: string, v: string) => t(`telemetry.${ns}.${v}`, { defaultValue: v })
  if (d && !d.devices.length) {
    return <Panel><EmptyState title={t('telemetry.emptyTitle')} desc={t('telemetry.empty')}
      action={canEdit ? <Button component={Link} to="/inventory/defaults" variant="default">{t('telemetry.turnOn')}</Button> : undefined} /></Panel>
  }
  const needle = q.trim().toLowerCase()
  const rows = (d?.devices ?? []).filter((x) => {
    const s = d!.seen[x.name]
    if (show === 'problems' && !s?.problems?.length) return false
    if (show === 'silent' && s?.seen) return false
    return !needle || [x.name, x.address, x.platform, agentName(x.agent)].some((v) => v.toLowerCase().includes(needle))
  })
  return (
    <Panel padding={0}>
      <Group justify="space-between" wrap="wrap" gap="sm" p="md" pb="xs">
        <TextInput leftSection={<IconSearch size={16} />} placeholder={t('telemetry.search')} aria-label={t('telemetry.search')}
          value={q} onChange={(e) => setQ(e.currentTarget.value)} w={{ base: '100%', sm: 280 }} />
        <SegmentedControl size="sm" value={show} onChange={(v) => setShow(v as Show)} aria-label={t('telemetry.show')}
          data={[{ value: 'all', label: t('telemetry.showAll') }, { value: 'problems', label: t('telemetry.showProblems') },
            { value: 'silent', label: t('telemetry.showSilent') }]} />
      </Group>
      <Table.ScrollContainer minWidth={640}>
        <Table highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('telemetry.device')}</Table.Th><Table.Th>{t('telemetry.drivers')}</Table.Th>
              <Table.Th visibleFrom="sm">{t('telemetry.agent')}</Table.Th><Table.Th>{t('telemetry.lastSeen')}</Table.Th>
              <Table.Th visibleFrom="md">{t('telemetry.what')}</Table.Th><Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((dev) => {
              const s = d!.seen[dev.name]
              return (
                <Table.Tr key={dev.id}>
                  <Table.Td>
                    <Text component={Link} to={telemetryPath(dev.inventory_id)} ff="monospace" size="sm" fw={600} c="inherit">{dev.name}</Text>
                    <Text size="xs" c="dimmed">{dev.address} · {label('platform', dev.platform)}</Text>
                    <DeviceProblems problems={s?.problems} />
                  </Table.Td>
                  <Table.Td><Group gap={4}>{dev.drivers.map((x) => <Badge key={x} variant="light" size="sm" tt="none">{label('driver', x)}</Badge>)}</Group></Table.Td>
                  <Table.Td visibleFrom="sm"><Text size="sm" c={dev.agent ? undefined : 'dimmed'}>{dev.agent ? agentName(dev.agent) : t('telemetry.anyAgent')}</Text></Table.Td>
                  <Table.Td>
                    {s?.seen ? <Badge color={s.online ? 'up' : 'down'} variant="light" tt="none" miw="max-content" title={dateTime(s.seen)}>{ago(s.seen)}</Badge>
                      : <Text size="sm" c="dimmed">{t('telemetry.never')}</Text>}
                  </Table.Td>
                  <Table.Td visibleFrom="md"><Text size="sm">{s?.ports !== undefined ? t('telemetry.counts', { ...s }) : '–'}</Text></Table.Td>
                  <Table.Td>
                    <Group gap={6} justify="flex-end" wrap="nowrap">
                      {isAdmin && d!.status.collector === 'agent' && <DeviceTelemetryActions name={dev.name} />}
                      <Tooltip label={canEdit ? t('telemetry.edit') : t('telemetry.open')}>
                        <ActionIcon component={Link} to={telemetryPath(dev.inventory_id)} variant="default"
                          aria-label={`${canEdit ? t('telemetry.edit') : t('telemetry.open')}: ${dev.name}`}><IconPencil size={16} /></ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {d && !rows.length && <Text size="sm" c="dimmed" p="md">{t('telemetry.noMatch')}</Text>}
    </Panel>
  )
}

/** Who collects, where it keeps the numbers, and what each agent counted. */
function Collector({ d }: { d: TelemetryOverview }) {
  const { t } = useTranslation()
  const errors = Object.entries({ ...d.status.poll_errors, ...d.status.storage.errors })
  return (
    <Stack gap="md">
      {errors.map(([what, msg]) => <Alert key={what} color="warn" title={what}>{msg}</Alert>)}
      <Panel title={t('telemetry.collector')}>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
          <Field label={t('telemetry.collector')}>{t(`telemetry.collectorIs.${d.status.collector}`)}</Field>
          <Field label={t('telemetry.storage')}>{t(`telemetry.storageIs.${d.status.storage.mode}`, { days: d.status.storage.keep_days })}</Field>
          <Field label={t('telemetry.devices')}>{d.status.devices}</Field>
          {d.status.points !== null && <Field label={t('telemetry.points')}>{d.status.points}</Field>}
        </SimpleGrid>
      </Panel>
      {d.status.agents && d.status.agents.length > 0 && (
        <Panel title={t('telemetry.agentsTitle')}><TelemetryAgentNumbersList agents={d.status.agents} /></Panel>
      )}
    </Stack>
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
    <Panel title={t('telemetry.sendersTitle')} desc={t('telemetry.senders')}>
      <Stack gap="sm">
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
    </Panel>
  )
}
