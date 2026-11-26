import { Badge, Group, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { FlowOwner, FlowsData } from '@/api/types'
import { DataTable, type DataColumn } from '@bitsandbricks/ui'
import { Panel } from '@/components/ui'
import { ago } from '@/lib/time'
import { bytes } from './format'

/** Who the hall's traffic goes to, by network (AS) and owner (issue #1481, A2). Aggregate only:
 *  an owner is named once five seats or more used it, like an application. */
export function TrafficOwners({ data }: { data: FlowsData }) {
  const { t } = useTranslation()
  const owners = data.owners ?? []
  const updated = data.owners_list?.updated
  const columns: DataColumn<FlowOwner>[] = [
    { id: 'name', header: t('trafficOwners.owner'), sort: (o) => o.name, cell: (o) => (
      <Group gap={6} wrap="nowrap">
        <span>{o.name}</span>
        <Badge size="xs" variant="light" color="gray" tt="none">AS{o.asn}</Badge>
      </Group>
    ) },
    { id: 'seats', header: t('traffic.svc.seats'), numeric: true, descFirst: true, sort: (o) => o.seats, cell: (o) => o.seats },
    { id: 'down', header: t('traffic.svc.down'), numeric: true, descFirst: true, sort: (o) => o.down, cell: (o) => bytes(o.down) },
    { id: 'up', header: t('traffic.svc.up'), numeric: true, descFirst: true, hideOnPhone: true, sort: (o) => o.up, cell: (o) => bytes(o.up) },
  ]
  return (
    <Panel className="fb-wide" titleId="traffic-owners" title={t('trafficOwners.title')}>
      {owners.length ? (
        <DataTable rows={owners} columns={columns} rowKey={(o) => String(o.asn)} label={t('trafficOwners.title')}
          urlState={false} bare density="compact" defaultSort={{ id: 'down', desc: true }} />
      ) : (
        <Text size="sm" c="dimmed">{updated ? t('trafficOwners.none') : t('trafficOwners.noList')}</Text>
      )}
      <Text size="xs" c="dimmed" mt={6}>
        {t('trafficOwners.text', { count: data.min_seats ?? 5, volume: bytes(data.other_owners ?? 0) })}
        {' '}
        {updated ? t('trafficOwners.source', { when: ago(updated) }) : t('trafficOwners.sourceNone')}
      </Text>
    </Panel>
  )
}
