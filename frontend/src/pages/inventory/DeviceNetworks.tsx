import { Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { DeviceDetail } from '@/api/types'
import { DataTable, EmptyState } from '@bitsandbricks/ui'
import { Panel } from '@/components/ui'
import { dateTime } from '@/lib/time'

type Discovered = NonNullable<DeviceDetail['discovered']>

/** The device's Networks and VLANs tab (issue #903): what discovery read from it, read-only. The
 *  inventory's own VLAN and range entries are made from these (Inventory → IP ranges). */
export function DeviceNetworks({ found }: { found: Discovered | undefined }) {
  const { t } = useTranslation()
  const vlans = found?.vlans ?? []
  const svis = found?.svis ?? []
  const routes = found?.routes ?? []
  // A network with its VLAN when a VLAN interface carries it.
  const vlanOf = new Map(svis.map((s) => [s.network, s.vlan]))
  const networks = [...new Set([...(found?.networks ?? []), ...svis.map((s) => s.network)])]
    .map((net) => ({ net, vlan: vlanOf.get(net) ?? null }))
  const nameOf = new Map(vlans.map((v) => [v.id, v.name]))
  if (!vlans.length && !networks.length && !routes.length) {
    return <EmptyState title={t('deviceNetworks.noneTitle')} description={t('deviceNetworks.none')} />
  }
  return (
    <Stack gap="md">
      {found?.at && <Text size="sm" c="dimmed">{t('deviceNetworks.readAt', { when: dateTime(Date.parse(found.at) / 1000) })}</Text>}
      {vlans.length > 0 && (
        <Panel title={t('deviceNetworks.vlans', { count: vlans.length })} padding={0}>
          <DataTable label={t('deviceNetworks.vlansLabel')} rows={vlans} rowKey={(v) => String(v.id)} defaultSort={{ id: 'id' }} bare
            columns={[
              { id: 'id', header: t('deviceNetworks.col.id'), width: 90, numeric: true, sort: (v) => v.id, cell: (v) => v.id },
              { id: 'name', header: t('deviceNetworks.col.name'), sort: (v) => v.name, cell: (v) => v.name || '–' },
              { id: 'nets', header: t('deviceNetworks.col.networks'), mono: true,
                cell: (v) => svis.filter((s) => s.vlan === v.id).map((s) => s.network).join(', ') || '–' },
            ]} />
        </Panel>
      )}
      {networks.length > 0 && (
        <Panel title={t('deviceNetworks.networks', { count: networks.length })} padding={0}>
          <DataTable label={t('deviceNetworks.networksLabel')} rows={networks} rowKey={(n) => n.net} defaultSort={{ id: 'net' }} bare
            columns={[
              { id: 'net', header: t('deviceNetworks.col.network'), mono: true, sort: (n) => n.net, cell: (n) => n.net },
              { id: 'vlan', header: t('deviceNetworks.col.vlan'), sort: (n) => n.vlan ?? -1,
                cell: (n) => (n.vlan == null ? '–' : nameOf.get(n.vlan) ? `${n.vlan} · ${nameOf.get(n.vlan)}` : n.vlan) },
            ]} />
        </Panel>
      )}
      {routes.length > 0 && (
        <Panel title={t('deviceNetworks.routes', { count: routes.length })} padding={0}>
          <DataTable label={t('deviceNetworks.routesLabel')} rows={routes} rowKey={(r, i) => `${r.network}|${r.next_hop}|${i}`} bare
            columns={[
              { id: 'net', header: t('deviceNetworks.col.network'), mono: true, sort: (r) => r.network, cell: (r) => r.network },
              { id: 'hop', header: t('deviceNetworks.col.nextHop'), mono: true, sort: (r) => r.next_hop ?? '', cell: (r) => r.next_hop || '–' },
              { id: 'if', header: t('deviceNetworks.col.interface'), sort: (r) => r.interface ?? '', cell: (r) => r.interface || '–' },
              { id: 'proto', header: t('deviceNetworks.col.proto'), hideOnPhone: true, sort: (r) => r.proto ?? '', cell: (r) => r.proto || '–' },
            ]} />
        </Panel>
      )}
    </Stack>
  )
}
