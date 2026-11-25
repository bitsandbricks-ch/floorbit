import { Badge, Group, SegmentedControl, Text, TextInput } from '@mantine/core'
import { DataTable, type DataColumn } from '@bitsandbricks/ui'
import { IconSearch } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { telemetryPath } from '@/pages/inventory/model'
import { ago, dateTime } from '@/lib/time'
import type { DeviceState, DeviceStateRow } from './api'
import { DeviceProblems, DeviceTelemetryActions } from './DeviceTelemetry'
import { NEEDS_LOOK, ORDER } from './state'

const STATE_COLOR: Record<DeviceState, string> = {
  silent: 'down', never: 'down', partial: 'warn', unknown: 'gray', waiting: 'gray', standby: 'gray', up: 'up',
}
export type DeviceFilter = 'all' | 'look'

/** Devices with their state, what came in and why one sends nothing, one row each. Shared by the
 *  agent's Devices tab and the Telemetry page, so both read the same. */
export function DeviceStateTable({ rows, filter, onFilter, actions = false, extra, agentOf, toolbar, rowEnd }: {
  rows: DeviceStateRow[]; filter: DeviceFilter; onFilter: (f: DeviceFilter) => void; actions?: boolean
  extra?: (row: DeviceStateRow) => React.ReactNode
  /** Adds an Agent column (the Telemetry page lists every agent's devices). */
  agentOf?: (row: DeviceStateRow) => React.ReactNode
  /** More filters, next to the search box. */
  toolbar?: React.ReactNode
  /** More buttons at the end of a row. */
  rowEnd?: (row: DeviceStateRow) => React.ReactNode
}) {
  const hasEnd = actions || !!rowEnd
  const { t } = useTranslation()
  const [q, setQ] = useState('')
  const label = (ns: string, v: string) => t(`telemetry.${ns}.${v}`, { defaultValue: v })
  const look = rows.filter((r) => NEEDS_LOOK.includes(r.state)).length
  const needle = q.trim().toLowerCase()
  const shown = rows.filter((r) => (filter === 'all' || NEEDS_LOOK.includes(r.state))
    && (!needle || [r.name, r.address, r.platform].some((v) => (v ?? '').toLowerCase().includes(needle))))
  const columns: DataColumn<DeviceStateRow>[] = [
    { id: 'name', header: t('telemetry.device'), sort: (r) => r.name, text: (r) => r.name, cell: (r) => (
      <>
        {r.inventory_id
          ? <Text component={Link} to={telemetryPath(r.inventory_id)} ff="monospace" size="sm" fw={600} c="inherit">{r.name}</Text>
          : <Text ff="monospace" size="sm" fw={600}>{r.name}</Text>}
        <Text size="xs" c="dimmed">{[r.address, r.platform && label('platform', r.platform)].filter(Boolean).join(' · ') || '–'}</Text>
        <DeviceProblems problems={r.problems} />
      </>
    ) },
    // Needs a look first, then by name, as the lists came before.
    { id: 'state', header: t('telemetry.state.col'), card: 'inline', sort: (r) => `${ORDER[r.state]}-${r.name.toLowerCase()}`,
      text: (r) => t(`telemetry.state.${r.state}`), cell: (r) => (
        <>
          <Badge variant="light" color={STATE_COLOR[r.state]} tt="none" miw="max-content">{t(`telemetry.state.${r.state}`)}</Badge>
          {r.pinned && <Text size="xs" c="dimmed">{t('telemetry.state.pinned')}</Text>}
          {r.pushed && <Text size="xs" c="dimmed">{t('telemetry.state.pushed')}</Text>}
          {extra?.(r)}
        </>
      ) },
    { id: 'drivers', header: t('telemetry.drivers'), card: 'label', text: (r) => r.drivers.map((x) => label('driver', x)).join(', '),
      cell: (r) => <Group gap={4}>{r.drivers.map((x) => <Badge key={x} variant="light" size="sm" tt="none">{label('driver', x)}</Badge>)}</Group> },
    ...(agentOf ? [{ id: 'agent', header: t('telemetry.agent'), card: 'label' as const, cell: (r: DeviceStateRow) => <Text size="sm">{agentOf(r)}</Text> }] : []),
    { id: 'seen', header: t('telemetry.lastSeen'), card: 'label', sort: (r) => r.seen ?? 0, descFirst: true,
      text: (r) => (r.seen ? dateTime(r.seen) : t('telemetry.never')),
      cell: (r) => (r.seen ? <Text size="sm" title={dateTime(r.seen)}>{ago(r.seen)}</Text> : <Text size="sm" c="dimmed">{t('telemetry.never')}</Text>) },
    { id: 'what', header: t('telemetry.what'), hideOnPhone: true, sort: (r) => r.ports ?? -1, descFirst: true,
      cell: (r) => <Text size="sm">{r.ports !== undefined ? t('telemetry.counts', { ports: r.ports, macs: r.macs ?? 0, arp: r.arp ?? 0, neighbours: r.neighbours ?? 0 }) : '–'}</Text> },
    ...(hasEnd ? [{ id: 'end', header: null, card: 'actions' as const, cell: (r: DeviceStateRow) => (
      <Group gap={6} justify="flex-end" wrap="nowrap">
        {actions && <DeviceTelemetryActions name={r.name} />}
        {rowEnd?.(r)}
      </Group>
    ) }] : []),
  ]
  return (
    <>
      <Group justify="space-between" wrap="wrap" gap="sm" p="md" pb="xs">
        <Group gap="sm" wrap="wrap" style={{ flex: 1 }}>
          <TextInput leftSection={<IconSearch size={16} />} placeholder={t('telemetry.search')} aria-label={t('telemetry.search')}
            value={q} onChange={(e) => setQ(e.currentTarget.value)} w={{ base: '100%', sm: 280 }} />
          {toolbar}
        </Group>
        <SegmentedControl size="sm" value={filter} onChange={(v) => onFilter(v as DeviceFilter)} aria-label={t('telemetry.show')}
          data={[{ value: 'all', label: t('telemetry.state.all', { count: rows.length }) },
            { value: 'look', label: t('telemetry.state.look', { count: look }) }]} />
      </Group>
      {/* Both pages keep their filters in the address already, so the table doesn't add its sort. */}
      <DataTable label={t('telemetry.state.table')} rows={shown} rowKey={(r) => r.name} columns={columns} bare cards
        defaultSort={{ id: 'state' }} urlState={false} minWidth={agentOf ? 900 : 800}
        rowProps={(r) => ({ id: `device-${r.name}` })}
        empty={<Text size="sm" c="dimmed" p="md">{filter === 'look' && !needle ? t('telemetry.state.allFine') : t('telemetry.noMatch')}</Text>} />
    </>
  )
}
