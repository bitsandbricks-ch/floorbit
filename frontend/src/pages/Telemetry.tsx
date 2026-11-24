import { ActionIcon, Alert, Button, Code, Group, Select, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core'
import { IconPencil } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { EntityOption } from '@/components/EntitySelect'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { PageTabs } from '@bitsandbricks/ui'
import { usePageTab } from '@/components/pageTab'
import { StatTile } from '@bitsandbricks/ui'
import { DeviceStateTable, type DeviceFilter } from '@/components/telemetry/DeviceStateTable'
import { NEEDS_LOOK, deviceRows } from '@/components/telemetry/state'
import type { DeviceSeen } from '@/components/telemetry/api'
import { TelemetryAgentNumbersList, type TelemetryAgentNumbers } from '@/components/telemetry/AgentNumbers'
import { EmptyState, Field, Panel } from '@/components/ui'
import { telemetryPath } from './inventory/model'
import { ConfirmButton } from '@bitsandbricks/ui'

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

/** Monitoring > Telemetry: what the collector hears from each device (docs/telemetry.md). Each
 *  device opens its own page (the inventory's Telemetry tab), where it is set up and tested. */
export default function Telemetry() {
  const { t } = useTranslation()
  const isAdmin = useCan('settings.manage')
  const data = useQuery({ queryKey: KEY, queryFn: () => get<TelemetryOverview>('/api/telemetry/overview'), refetchInterval: 15_000 })
  const d = data.data
  const [tab, setTab] = usePageTab(['devices', 'collector', ...(isAdmin ? ['senders'] : [])])
  // A device that never reported needs a look as much as one with an error (issue #1014).
  const problems = d ? deviceRows(d).filter((r) => NEEDS_LOOK.includes(r.state)).length : 0
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
            <StatTile label={t('telemetry.devicesTitle')} value={String(d.devices.length)}
              sub={t(`telemetry.collectorIs.${d.status.collector}`)} />
            <StatTile label={t('telemetry.heardCard')} value={`${d.devices.length - silent} / ${d.devices.length}`}
              tone={!d.devices.length ? undefined : silent ? (silent === d.devices.length ? 'err' : 'warn') : 'ok'} />
            <StatTile label={t('telemetry.problemsCard')} value={String(problems)} tone={problems ? 'warn' : undefined}
              sub={problems ? undefined : t('telemetry.noProblems')} />
            <StatTile label={t('telemetry.points')} value={d.status.points !== null ? String(d.status.points) : '–'}
              tone={Object.keys(d.status.storage.errors).length ? 'err' : undefined}
              sub={t(`telemetry.storageIs.${d.status.storage.mode}`, { days: d.status.storage.keep_days })} />
          </SimpleGrid>
        )}
        <PageTabs label={t('telemetry.title')} active={tab} onChange={setTab} tabs={[
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
  const [params, setParams] = useSearchParams()
  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const filter: DeviceFilter = params.get('show') === 'look' ? 'look' : 'all'
  const agent = params.get('agent'), driver = params.get('driver')
  const label = (ns: string, v: string) => t(`telemetry.${ns}.${v}`, { defaultValue: v })
  if (d && !d.devices.length && !Object.keys(d.seen).length) {
    return <Panel><EmptyState title={t('telemetry.emptyTitle')} desc={t('telemetry.empty')}
      action={canEdit ? <Button component={Link} to="/inventory/defaults" variant="default">{t('telemetry.turnOn')}</Button> : undefined} /></Panel>
  }
  const all = d ? deviceRows(d) : []
  const agentOf = new Map((d?.devices ?? []).map((x) => [x.name, x.agent]))
  const rows = all.filter((r) => (!agent || (agent === '-' ? !agentOf.get(r.name) : agentOf.get(r.name) === agent))
    && (!driver || r.drivers.includes(driver)))
  const agentIds = [...new Set((d?.devices ?? []).map((x) => x.agent).filter(Boolean))]
  const drivers = [...new Set(all.flatMap((r) => r.drivers))].sort()
  return (
    <Panel padding={0}>
      <DeviceStateTable rows={rows} filter={filter} onFilter={(f) => set('show', f === 'look' ? 'look' : null)}
        actions={isAdmin && d?.status.collector === 'agent'}
        agentOf={(r) => r.pushed ? <Text span size="sm" c="dimmed">–</Text>
          : agentOf.get(r.name) ? agentName(agentOf.get(r.name)!) : <Text span size="sm" c="dimmed">{t('telemetry.anyAgent')}</Text>}
        toolbar={<>
          {agentIds.length > 0 && (
            <Select size="sm" w={180} clearable placeholder={t('telemetry.allAgents')} aria-label={t('telemetry.agent')} value={agent}
              onChange={(v) => set('agent', v)}
              data={[...agentIds.map((id) => ({ value: id, label: agentName(id) })), { value: '-', label: t('telemetry.anyAgent') }]} />
          )}
          {drivers.length > 1 && (
            <Select size="sm" w={180} clearable placeholder={t('telemetry.allDrivers')} aria-label={t('telemetry.drivers')} value={driver}
              onChange={(v) => set('driver', v)} data={drivers.map((x) => ({ value: x, label: label('driver', x) }))} />
          )}
        </>}
        rowEnd={(r) => r.inventory_id && (
          <Tooltip label={canEdit ? t('telemetry.edit') : t('telemetry.open')}>
            <ActionIcon component={Link} to={telemetryPath(r.inventory_id)} variant="default"
              aria-label={`${canEdit ? t('telemetry.edit') : t('telemetry.open')}: ${r.name}`}><IconPencil size={16} /></ActionIcon>
          </Tooltip>
        )} />
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
