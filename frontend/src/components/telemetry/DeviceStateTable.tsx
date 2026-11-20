import { Badge, Group, SegmentedControl, Table, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { telemetryPath } from '@/pages/inventory/model'
import { ago, dateTime } from '@/lib/time'
import type { DeviceState, DeviceStateRow } from './api'
import { DeviceProblems, DeviceTelemetryActions } from './DeviceTelemetry'

const STATE_COLOR: Record<DeviceState, string> = {
  silent: 'down', never: 'down', partial: 'warn', unknown: 'gray', waiting: 'gray', standby: 'gray', up: 'up',
}
const NEEDS_LOOK: DeviceState[] = ['silent', 'never', 'partial']
export type DeviceFilter = 'all' | 'look'

/** Devices with their state, what came in and why one sends nothing, one row each. Shared by the
 *  agent's Devices tab and the Telemetry page, so both read the same. */
export function DeviceStateTable({ rows, filter, onFilter, actions = false, extra }: {
  rows: DeviceStateRow[]; filter: DeviceFilter; onFilter: (f: DeviceFilter) => void; actions?: boolean
  extra?: (row: DeviceStateRow) => React.ReactNode
}) {
  const { t } = useTranslation()
  const [q, setQ] = useState('')
  const label = (ns: string, v: string) => t(`telemetry.${ns}.${v}`, { defaultValue: v })
  const look = rows.filter((r) => NEEDS_LOOK.includes(r.state)).length
  const needle = q.trim().toLowerCase()
  const shown = rows.filter((r) => (filter === 'all' || NEEDS_LOOK.includes(r.state))
    && (!needle || [r.name, r.address, r.platform].some((v) => (v ?? '').toLowerCase().includes(needle))))
  return (
    <>
      <Group justify="space-between" wrap="wrap" gap="sm" p="md" pb="xs">
        <TextInput leftSection={<IconSearch size={16} />} placeholder={t('telemetry.search')} aria-label={t('telemetry.search')}
          value={q} onChange={(e) => setQ(e.currentTarget.value)} w={{ base: '100%', sm: 280 }} />
        <SegmentedControl size="sm" value={filter} onChange={(v) => onFilter(v as DeviceFilter)} aria-label={t('telemetry.show')}
          data={[{ value: 'all', label: t('telemetry.state.all', { count: rows.length }) },
            { value: 'look', label: t('telemetry.state.look', { count: look }) }]} />
      </Group>
      <Table.ScrollContainer minWidth={640}>
        <Table verticalSpacing="sm" aria-label={t('telemetry.state.table')}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('telemetry.device')}</Table.Th><Table.Th>{t('telemetry.state.col')}</Table.Th>
              <Table.Th>{t('telemetry.drivers')}</Table.Th><Table.Th>{t('telemetry.lastSeen')}</Table.Th>
              <Table.Th visibleFrom="md">{t('telemetry.what')}</Table.Th>{actions && <Table.Th />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {shown.map((r) => (
              <Table.Tr key={r.name} id={`device-${r.name}`}>
                <Table.Td>
                  {r.inventory_id
                    ? <Text component={Link} to={telemetryPath(r.inventory_id)} ff="monospace" size="sm" fw={600} c="inherit">{r.name}</Text>
                    : <Text ff="monospace" size="sm" fw={600}>{r.name}</Text>}
                  <Text size="xs" c="dimmed">{[r.address, r.platform && label('platform', r.platform)].filter(Boolean).join(' · ') || '–'}</Text>
                  <DeviceProblems problems={r.problems} />
                </Table.Td>
                <Table.Td>
                  <Badge variant="light" color={STATE_COLOR[r.state]} tt="none" miw="max-content">{t(`telemetry.state.${r.state}`)}</Badge>
                  {r.pinned && <Text size="xs" c="dimmed">{t('telemetry.state.pinned')}</Text>}
                  {r.pushed && <Text size="xs" c="dimmed">{t('telemetry.state.pushed')}</Text>}
                  {extra?.(r)}
                </Table.Td>
                <Table.Td><Group gap={4}>{r.drivers.map((x) => <Badge key={x} variant="light" size="sm" tt="none">{label('driver', x)}</Badge>)}</Group></Table.Td>
                <Table.Td>
                  {r.seen ? <Text size="sm" title={dateTime(r.seen)}>{ago(r.seen)}</Text> : <Text size="sm" c="dimmed">{t('telemetry.never')}</Text>}
                </Table.Td>
                <Table.Td visibleFrom="md"><Text size="sm">{r.ports !== undefined ? t('telemetry.counts', { ports: r.ports, macs: r.macs ?? 0, arp: r.arp ?? 0, neighbours: r.neighbours ?? 0 }) : '–'}</Text></Table.Td>
                {actions && <Table.Td><Group gap={6} justify="flex-end" wrap="nowrap"><DeviceTelemetryActions name={r.name} /></Group></Table.Td>}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {!shown.length && <Text size="sm" c="dimmed" p="md">{filter === 'look' && !needle ? t('telemetry.state.allFine') : t('telemetry.noMatch')}</Text>}
    </>
  )
}
