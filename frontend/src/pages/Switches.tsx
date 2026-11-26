import { Anchor, Group, Text } from '@mantine/core'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useInventory } from '@/api/queries'
import { useLiveEvent } from '@/api/live'
import { useQueryClient } from '@tanstack/react-query'
import { qk } from '@/api/keys'
import { Layout } from '@/components/Layout'
import {
  type DataColumn, DataTable, ErrorBanner, FilterBar, LoadingState, PageHead, StatGrid, StatTile, StatusBadge,
  UsageBar, useFilters,
} from '@bitsandbricks/ui'
import { LastDayCell, UplinkCell } from './inventory/ListCells'
import { lastDaySort, uplinkSort } from './inventory/listColumns'
import { devicePath } from './inventory/model'
import { switchRows, type SwitchRow, TIERS } from './switches/rows'

/** Network › Switches (issue #902): the inventory's switches with their live columns, so a crew
 *  sees which one is down, which uplink is full and how much PoE is left without opening each. */
export default function Switches() {
  const { t, i18n } = useTranslation()
  const q = useInventory(false)
  const client = useQueryClient()
  useLiveEvent('monitor.poll', () => void client.invalidateQueries({ queryKey: qk.inventory(false) }))
  const all = useMemo(() => switchRows(q.data?.devices ?? []), [q.data])
  const filters = useFilters({ tier: 'all', state: 'all', hall: 'all' })
  const halls = [...new Set(all.map((r) => r.d.hall).filter(Boolean))].sort()
  const needle = filters.search.trim().toLowerCase()
  const rows = all.filter((r) => (filters.values.tier === 'all' || r.tier === filters.values.tier)
    && (filters.values.state === 'all' || r.state === filters.values.state)
    && (filters.values.hall === 'all' || r.d.hall === filters.values.hall)
    && (!needle || [r.d.name, r.d.model, r.d.mgmt_ip, r.d.hall].some((v) => (v ?? '').toLowerCase().includes(needle))))
  const num = (n: number) => n.toLocaleString(i18n.language)

  const columns: DataColumn<SwitchRow>[] = [
    { id: 'name', header: t('switches.col.name'), sort: (r) => r.d.name, cell: (r) => (
      <Group gap={6} wrap="nowrap">
        <Anchor component={Link} to={devicePath(r.d.id)} ff="monospace" fw={600}>{r.d.name}</Anchor>
        {r.tier && <Text span size="xs" c="dimmed">{t(`switches.tier.${r.tier}`)}</Text>}
      </Group>
    ) },
    { id: 'state', header: t('switches.col.state'), sort: (r) => ['down', 'errors', 'unknown', 'up'].indexOf(r.state),
      cell: (r) => <StatusBadge state={r.state === 'up' ? 'online' : r.state === 'down' ? 'offline' : r.state === 'errors' ? 'warn' : 'unknown'}
        label={t(`switches.state.${r.state}`)} /> },
    { id: 'seats', header: t('switches.col.seats'), sort: (r) => r.d.seats ?? 0, descFirst: true, mono: true,
      cell: (r) => (r.d.seats ? num(r.d.seats) : '–') },
    { id: 'ports', header: t('switches.col.ports'), sort: (r) => (r.d.ports ? r.d.ports.up / Math.max(1, r.d.ports.total) : -1), mono: true,
      cell: (r) => (r.d.ports ? `${r.d.ports.up} / ${r.d.ports.total}` : '–') },
    { id: 'uplink', header: t('switches.col.uplink'), sort: (r) => uplinkSort(r.d), hideOnPhone: true, cell: (r) => (
      r.d.uplink
        ? <Group gap={6} wrap="nowrap"><Text span size="sm" ff="monospace" c="dimmed">{r.d.uplink.peer} ·</Text><UplinkCell d={r.d} /></Group>
        : <Text span c="dimmed">–</Text>
    ) },
    { id: 'load', header: t('switches.col.load'), sort: (r) => r.d.uplink?.load ?? -1, descFirst: true, hideOnPhone: true,
      cell: (r) => <UsageBar value={r.d.uplink?.load != null ? Math.round(r.d.uplink.load * 100) : null} label={t('switches.col.load')} warnAt={70} errAt={90} /> },
    { id: 'poe', header: t('switches.col.poe'), sort: (r) => r.d.poe?.used_w ?? -1, descFirst: true, mono: true, hideOnPhone: true,
      cell: (r) => (r.d.poe ? t('switches.poe', { used: num(Math.round(r.d.poe.used_w)), budget: num(Math.round(r.d.poe.budget_w)) }) : '–') },
    { id: 'last_day', header: t('switches.col.lastDay'), sort: (r) => lastDaySort(r.d), descFirst: true, hideOnPhone: true,
      cell: (r) => <LastDayCell d={r.d} /> },
  ]

  return (
    <Layout title={t('switches.title')}>
      <PageHead title={t('switches.title')} desc={t('switches.intro')} />
      {q.error && <ErrorBanner error={q.error} />}
      {!q.data && !q.error && <LoadingState />}
      {q.data && (
        <>
          <Figures rows={all} />
          <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('switches.search')} onClear={filters.clear}
            groups={filters.groups([
              { key: 'tier', label: t('switches.filter.tier'), hidden: new Set(all.map((r) => r.tier)).size < 2,
                options: ['all', ...TIERS].map((v) => ({ value: v, label: v === 'all' ? t('switches.filter.any') : t(`switches.tier.${v}`),
                  count: v === 'all' ? all.length : all.filter((r) => r.tier === v).length })) },
              { key: 'state', label: t('switches.filter.state'),
                options: ['all', 'up', 'errors', 'down', 'unknown'].map((v) => ({ value: v, label: v === 'all' ? t('switches.filter.any') : t(`switches.state.${v}`),
                  count: v === 'all' ? all.length : all.filter((r) => r.state === v).length })) },
              { key: 'hall', label: t('switches.filter.hall'), hidden: halls.length < 2,
                options: ['all', ...halls].map((v) => ({ value: v, label: v === 'all' ? t('switches.filter.any') : v })) },
            ])}
            actions={<Anchor component={Link} to="/inventory?role=switch" size="sm">{t('switches.inInventory')}</Anchor>} />
          <DataTable rows={rows} columns={columns} rowKey={(r) => r.d.id} label={t('switches.title')} urlState cards
            defaultSort={{ id: 'state' }} minWidth={960}
            empty={all.length ? t('switches.noMatch') : t('switches.none')} />
          <Text size="xs" c="dimmed" mt="sm">{t('switches.foot')}</Text>
        </>
      )}
    </Layout>
  )
}

function Figures({ rows }: { rows: SwitchRow[] }) {
  const { t, i18n } = useTranslation()
  const num = (n: number) => n.toLocaleString(i18n.language)
  const known = rows.filter((r) => r.state !== 'unknown')
  const down = rows.filter((r) => r.state === 'down')
  const seatsDown = down.reduce((n, r) => n + (r.d.seats ?? 0), 0)
  const access = rows.filter((r) => r.d.ports && (r.d.seats ?? 0) > 0)
  const portsUp = access.reduce((n, r) => n + (r.d.ports?.up ?? 0), 0)
  const portsAll = access.reduce((n, r) => n + (r.d.ports?.total ?? 0), 0)
  const busiest = rows.filter((r) => r.d.uplink?.load != null).sort((a, b) => (b.d.uplink!.load! - a.d.uplink!.load!))[0]
  const poe = rows.filter((r) => r.d.poe)
  const used = poe.reduce((n, r) => n + (r.d.poe?.used_w ?? 0), 0)
  const budget = poe.reduce((n, r) => n + (r.d.poe?.budget_w ?? 0), 0)
  const load = busiest ? Math.round(busiest.d.uplink!.load! * 100) : null
  return (
    <StatGrid columns={4}>
      <StatTile label={t('switches.fig.up')} value={known.length ? `${known.length - down.length} / ${rows.length}` : '–'}
        tone={!known.length ? undefined : down.length ? 'err' : 'ok'}
        sub={down.length
          ? t('switches.fig.down', { names: down.slice(0, 3).map((r) => r.d.name).join(', '), count: seatsDown })
          : known.length ? t('switches.fig.allUp') : t('switches.fig.notRead')} />
      <StatTile label={t('switches.fig.ports')} value={portsAll ? `${num(portsUp)} / ${num(portsAll)}` : '–'}
        sub={t('switches.fig.portsSub')} />
      <StatTile label={t('switches.fig.busiest')} value={load != null ? `${load} %` : '–'}
        tone={load == null ? undefined : load >= 90 ? 'err' : load >= 70 ? 'warn' : undefined}
        sub={busiest ? `${busiest.d.name} → ${busiest.d.uplink!.peer}` : t('switches.fig.noLoad')} />
      <StatTile label={t('switches.fig.poe')} value={poe.length ? `${num(Math.round(used))} W` : '–'}
        sub={poe.length ? t('switches.fig.poeSub', { budget: num(Math.round(budget)) }) : t('switches.fig.noPoe')} />
    </StatGrid>
  )
}

