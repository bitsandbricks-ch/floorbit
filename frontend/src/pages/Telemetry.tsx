import { Alert, Button, Code, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { EntityOption } from '@/components/EntitySelect'
import { Layout } from '@/components/Layout'
import { Card, ConfirmButton, EmptyState, FilterBar, PageHead, PageTabs, PanelField, StatTile, useFilters } from '@bitsandbricks/ui'
import { usePageTab } from '@/components/pageTab'
import { MethodGrid, type GridRow } from '@/components/telemetry/MethodGrid'
import { methodCells, rowNeedsLook } from '@/components/telemetry/methods'
import { NEEDS_LOOK, deviceRows } from '@/components/telemetry/state'
import type { DeviceSeen } from '@/components/telemetry/api'
import { TelemetryAgentNumbersList, type TelemetryAgentNumbers } from '@/components/telemetry/AgentNumbers'

/** A device telemetry collects from: an inventory device with the Telemetry feature on. No logins. */
export interface TelemetryDevice {
  id: string; name: string; address: string; kind: string; platform: string; drivers: string[]
  agent: string; inventory_id: string; ports: { snmp?: number; gnmi?: number; api?: number }
}
/** GET /api/telemetry/overview (floorbit/blueprints/telemetry.py). */
export interface TelemetryOverview {
  devices: TelemetryDevice[]; seen: Record<string, DeviceSeen>
  /** When each device's last syslog line came (issue #904). */
  syslog?: Record<string, number>
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
  const errors = d ? Object.keys({ ...d.status.poll_errors, ...d.status.storage.errors }).length : 0

  return (
    <Layout title={t('telemetry.title')}>
      <PageHead title={t('telemetry.title')} desc={t('telemetry.intro')}
        actions={<Button component={Link} to="/inventory" variant="default">{t('telemetry.openInventory')}</Button>} />
      <Stack gap="md">
        {data.error && <Alert color="down" role="alert">{data.error.message}</Alert>}
        {d && <Figures d={d} />}
        <PageTabs label={t('telemetry.title')} active={tab} onChange={setTab} tabs={[
          { id: 'devices', label: t('telemetry.devicesTitle'), count: d?.devices.length },
          { id: 'collector', label: t('telemetry.collectorTab'), alert: errors ? 'warn' : null },
          ...(isAdmin ? [{ id: 'senders', label: t('telemetry.sendersTitle') }] : []),
        ]} />
        {tab === 'devices' && <Devices d={d} />}
        {tab === 'collector' && d && <Collector d={d} />}
        {tab === 'senders' && isAdmin && <Senders collector={d?.status.collector} />}
      </Stack>
    </Layout>
  )
}

/** Devices heard, points, refused writes and storage: the collector at a glance (issue #904). */
function Figures({ d }: { d: TelemetryOverview }) {
  const { t, i18n } = useTranslation()
  const rows = deviceRows(d)
  const never = rows.filter((r) => r.state === 'never').length
  const late = rows.filter((r) => r.state === 'silent' || r.state === 'partial').length
  const heard = rows.filter((r) => r.seen).length
  const refused = Object.entries(d.status.storage.errors)
  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm" aria-label={t('telemetry.summary')}>
      <StatTile label={t('telemetryGrid.fig.heard')} value={`${heard} / ${rows.length}`}
        tone={!rows.length ? undefined : never + late ? (heard ? 'warn' : 'err') : 'ok'}
        sub={never + late ? t('telemetryGrid.fig.heardSub', { never, late }) : t('telemetry.noProblems')} />
      <StatTile label={t('telemetry.points')} value={d.status.points !== null ? d.status.points.toLocaleString(i18n.language) : '–'}
        sub={t(`telemetry.collectorIs.${d.status.collector}`)} />
      <StatTile label={t('telemetryGrid.fig.refused')} value={String(refused.length)} tone={refused.length ? 'err' : undefined}
        sub={refused.length ? refused[0][1] : t('telemetryGrid.fig.refusedNone')} />
      <StatTile label={t('telemetryGrid.fig.kept')}
        value={d.status.storage.keep_days ? t('telemetryGrid.fig.days', { count: d.status.storage.keep_days }) : '–'}
        sub={t(`telemetry.storageIs.${d.status.storage.mode}`, { days: d.status.storage.keep_days })} />
    </SimpleGrid>
  )
}

function Devices({ d }: { d?: TelemetryOverview }) {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  // The same cached list the inventory's agent field shows: an agent by its name.
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') })
  const agentName = (id: string) => agents.data?.options.find((o) => o.value === id)?.label ?? id
  const filters = useFilters({ show: 'look', agent: '' })
  if (d && !d.devices.length && !Object.keys(d.seen).length) {
    return <Card heading={2}><EmptyState title={t('telemetry.emptyTitle')} description={t('telemetry.empty')}
      action={canEdit ? <Button component={Link} to="/inventory/defaults" variant="default">{t('telemetry.turnOn')}</Button> : undefined} /></Card>
  }
  const agentOf = new Map((d?.devices ?? []).map((x) => [x.name, x.agent]))
  const all: GridRow[] = (d ? deviceRows(d) : []).map((r) => {
    const id = agentOf.get(r.name)
    return { r, cells: methodCells(r, d?.syslog?.[r.name]), agentSort: id ? agentName(id) : '',
      agent: r.pushed ? <Text span size="sm" c="dimmed">–</Text>
        : id ? agentName(id) : <Text span size="sm" c="dimmed">{t('telemetry.anyAgent')}</Text> }
  })
  const look = all.filter((g) => rowNeedsLook(g.cells) || NEEDS_LOOK.includes(g.r.state))
  const never = all.filter((g) => g.r.state === 'never')
  const { show, agent } = filters.values
  const needle = filters.search.trim().toLowerCase()
  const rows = (show === 'look' && look.length ? look : show === 'never' ? never : all)
    .filter((g) => (!agent || (agent === '-' ? !agentOf.get(g.r.name) : agentOf.get(g.r.name) === agent))
      && (!needle || [g.r.name, g.r.address, g.r.kind].some((v) => (v ?? '').toLowerCase().includes(needle))))
  const agentIds = [...new Set((d?.devices ?? []).map((x) => x.agent).filter(Boolean))]
  return (
    <Stack gap="sm">
      <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('telemetry.search')} onClear={filters.clear}
        groups={filters.groups([
          { key: 'show', label: t('telemetry.show'), options: [
            { value: 'all', label: t('telemetryGrid.filter.all'), count: all.length },
            { value: 'look', label: t('telemetryGrid.filter.look'), count: look.length },
            { value: 'never', label: t('telemetryGrid.filter.never'), count: never.length },
          ] },
          { key: 'agent', label: t('telemetry.agent'), hidden: !agentIds.length, options: [
            { value: '', label: t('telemetry.allAgents') },
            ...agentIds.map((id) => ({ value: id, label: agentName(id) })),
            { value: '-', label: t('telemetry.anyAgent') },
          ] },
        ])} />
      {show === 'look' && !look.length && all.length > 0 && <Text size="sm" c="dimmed">{t('telemetryGrid.allGood')}</Text>}
      <Card heading={2}><MethodGrid rows={rows} /></Card>
    </Stack>
  )
}

/** Who collects, where it keeps the numbers, and what each agent counted. */
function Collector({ d }: { d: TelemetryOverview }) {
  const { t } = useTranslation()
  const errors = Object.entries({ ...d.status.poll_errors, ...d.status.storage.errors })
  return (
    <Stack gap="md">
      {errors.map(([what, msg]) => <Alert key={what} color="warn" title={what}>{msg}</Alert>)}
      <Card heading={2} title={t('telemetry.collector')}>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
          <PanelField label={t('telemetry.collector')}>{t(`telemetry.collectorIs.${d.status.collector}`)}</PanelField>
          <PanelField label={t('telemetry.storage')}>{t(`telemetry.storageIs.${d.status.storage.mode}`, { days: d.status.storage.keep_days })}</PanelField>
          <PanelField label={t('telemetry.devices')}>{d.status.devices}</PanelField>
          {d.status.points !== null && <PanelField label={t('telemetry.points')}>{d.status.points}</PanelField>}
        </SimpleGrid>
      </Card>
      {d.status.agents && d.status.agents.length > 0 && (
        <Card heading={2} title={t('telemetry.agentsTitle')}><TelemetryAgentNumbersList agents={d.status.agents} /></Card>
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
    <Card heading={2} title={t('telemetry.sendersTitle')} desc={t('telemetry.senders')}>
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
    </Card>
  )
}
