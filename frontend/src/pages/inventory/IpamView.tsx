import { Alert, Anchor, Badge, Button, Group, SegmentedControl, Select, Switch, Text, TextInput } from '@mantine/core'
import { IconPlus, IconSearch } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { FirewallList, FirewallRange, InventoryEntry, InventoryType } from '@/api/types'
import { DataTable } from '@/components/DataTable'
import { LoadingState } from '@/components/ui'
import { ROUTE_TONE } from '@/pages/firewalls/scope'
import { AddEntry } from './EntriesView'
import { entryPath } from './model'
import { useEntries } from './scope'
import { ipNum, vlanNum, type IpamSub } from './ipam'

/** IPAM (issue #1346): the inventory's VLANs and prefixes on one tab. A firewall range is a prefix
 *  with firewalls set, so the Prefixes list shows its firewalls and how its route is doing now. */
export function IpamView({ types, sub, onSub, canEdit, sourceName }: {
  types: InventoryType[]; sub: IpamSub; onSub: (s: IpamSub) => void; canEdit: boolean; sourceName: (id: string) => string
}) {
  const { t } = useTranslation()
  const vlanType = types.find((x) => x.id === 'vlan')
  const prefixType = types.find((x) => x.id === 'prefix')
  const vlans = useEntries('vlan')
  const prefixes = useEntries('prefix')
  const navigate = useNavigate()
  const fw = useQuery({ queryKey: qk.firewalls, queryFn: () => get<FirewallList>('/api/firewalls'), refetchInterval: 15_000 })
  const [query, setQuery] = useState('')
  const [purpose, setPurpose] = useState<string | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const [withFirewalls, setWithFirewalls] = useState(false)
  const [adding, setAdding] = useState(false)

  const vlanRows = vlans.data?.entries ?? []
  const prefixRows = prefixes.data?.entries ?? []
  const ranges = new Map<string, FirewallRange>((fw.data?.ranges ?? []).map((r) => [r.id, r]))
  const vlanById = new Map(vlanRows.filter((v) => v.fields.vlan_id).map((v) => [v.fields.vlan_id, v]))
  const prefixesOf = (vid: string) => prefixRows.filter((p) => vid && p.fields.vlan_id === vid)
  const rows = sub === 'vlans' ? vlanRows : prefixRows
  const purposes = [...new Set(rows.map((e) => e.fields.purpose).filter(Boolean))].sort()
  const sourceIds = [...new Set(rows.flatMap((e) => e.sources ?? []))]
  const q = query.trim().toLowerCase()
  const shown = rows.filter((e) => {
    if (q && ![e.name, e.notes, ...Object.values(e.fields)].some((v) => (v || '').toLowerCase().includes(q))) return false
    if (purpose && e.fields.purpose !== purpose) return false
    if (source === 'manual' && e.sources?.length) return false
    if (source && source !== 'manual' && !e.sources?.includes(source)) return false
    if (sub === 'prefixes' && withFirewalls && !ranges.has(e.id)) return false
    return true
  })
  const sources = (e: InventoryEntry) => (
    <Group gap={4} wrap="nowrap">
      {!e.sources?.length && <Badge variant="outline" color="gray" tt="none">{t('inventory.manual')}</Badge>}
      {e.sources?.map((s) => (
        <Badge key={s} variant={e.gone?.includes(s) ? 'outline' : 'light'} color={e.gone?.includes(s) ? 'warn' : 'trace'} tt="none">
          {e.gone?.includes(s) ? t('inventory.gone', { source: sourceName(s) }) : sourceName(s)}
        </Badge>
      ))}
    </Group>
  )
  const addType = sub === 'vlans' ? vlanType : prefixType
  const pending = vlans.isPending || prefixes.isPending
  const error = vlans.error ?? prefixes.error

  return (
    <>
      <Group gap="sm" mb="md" wrap="wrap">
        <SegmentedControl value={sub} onChange={(v) => { onSub(v as IpamSub); setPurpose(null); setSource(null) }}
          aria-label={t('ipam.title')}
          data={[
            { value: 'vlans', label: `${t('ipam.vlans')} ${vlanRows.length}` },
            { value: 'prefixes', label: `${t('ipam.prefixes')} ${prefixRows.length}` },
          ]} />
        <TextInput aria-label={t('inventory.search')} placeholder={t('ipam.search')} leftSection={<IconSearch size={16} />}
          value={query} onChange={(e) => setQuery(e.currentTarget.value)} style={{ flex: '1 1 220px', maxWidth: 320 }} />
        <Select aria-label={t('ipam.col.purpose')} placeholder={t('ipam.anyPurpose')} clearable w={160}
          data={purposes} value={purpose} onChange={setPurpose} />
        <Select aria-label={t('ipam.col.source')} placeholder={t('ipam.anySource')} clearable w={160}
          data={[{ value: 'manual', label: t('inventory.manual') }, ...sourceIds.map((s) => ({ value: s, label: sourceName(s) }))]}
          value={source} onChange={setSource} />
        {sub === 'prefixes' && (
          <Switch label={t('ipam.withFirewalls')} checked={withFirewalls} onChange={(e) => setWithFirewalls(e.currentTarget.checked)} />
        )}
        {canEdit && addType && (
          <Button ml="auto" leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            {sub === 'vlans' ? t('ipam.addVlan') : t('ipam.addPrefix')}
          </Button>
        )}
      </Group>
      {pending && <LoadingState />}
      {error && <Alert color="down" role="alert">{t('common.error', { message: error.message })}</Alert>}
      {!pending && !error && sub === 'vlans' && (
        <DataTable label={t('ipam.vlans')} rows={shown} rowKey={(e) => e.id} defaultSort={{ id: 'vlan' }} minWidth={640}
          empty={<Text c="dimmed">{vlanRows.length ? t('inventory.noMatch') : t('ipam.noVlans')}</Text>}
          count={(n) => t('ipam.vlanCount', { count: n })}
          columns={[
            { id: 'vlan', header: t('ipam.col.vlan'), mono: true, width: 90, sort: (e) => vlanNum(e.fields.vlan_id), cell: (e) => e.fields.vlan_id || '–' },
            { id: 'name', header: t('inventory.field.name'), sort: (e) => e.name,
              cell: (e) => <Anchor component={Link} to={entryPath('vlan', e.id)} fw={600}>{e.name}</Anchor> },
            { id: 'purpose', header: t('ipam.col.purpose'), sort: (e) => e.fields.purpose ?? '', cell: (e) => e.fields.purpose || '' },
            { id: 'prefixes', header: t('ipam.prefixes'), wrap: true, hideOnPhone: true, sort: (e) => prefixesOf(e.fields.vlan_id).length,
              cell: (e) => (
                <Group gap={8}>
                  {prefixesOf(e.fields.vlan_id).map((p) => (
                    <Anchor key={p.id} component={Link} to={entryPath('prefix', p.id)} size="sm" ff="monospace">{p.fields.prefix || p.name}</Anchor>
                  ))}
                </Group>
              ) },
            { id: 'source', header: t('ipam.col.source'), hideOnPhone: true, cell: sources },
          ]} />
      )}
      {!pending && !error && sub === 'prefixes' && (
        <DataTable label={t('ipam.prefixes')} rows={shown} rowKey={(e) => e.id} defaultSort={{ id: 'prefix' }} minWidth={760}
          empty={<Text c="dimmed">{prefixRows.length ? t('inventory.noMatch') : t('ipam.noPrefixes')}</Text>}
          count={(n) => t('ipam.prefixCount', { count: n })}
          columns={[
            { id: 'prefix', header: t('ipam.col.prefix'), sort: (e) => ipNum(e.fields.prefix || e.name), cell: (e) => (
              <>
                <Anchor component={Link} to={entryPath('prefix', e.id)} fw={600} ff="monospace">{e.fields.prefix || e.name}</Anchor>
                {e.fields.prefix && e.name !== e.fields.prefix && <Text size="xs" c="dimmed">{e.name}</Text>}
              </>
            ) },
            { id: 'vlan', header: t('ipam.col.vlan'), sort: (e) => vlanNum(e.fields.vlan_id), cell: (e) => {
              const v = vlanById.get(e.fields.vlan_id)
              if (!e.fields.vlan_id) return '–'
              return v ? <Anchor component={Link} to={entryPath('vlan', v.id)} size="sm">{e.fields.vlan_id} · {v.name}</Anchor>
                : <Text size="sm" ff="monospace">{e.fields.vlan_id}</Text>
            } },
            { id: 'purpose', header: t('ipam.col.purpose'), sort: (e) => e.fields.purpose ?? '', cell: (e) => e.fields.purpose || '' },
            { id: 'firewalls', header: t('ipam.col.firewalls'), wrap: true, sort: (e) => ranges.get(e.id)?.firewalls.length ?? 0, descFirst: true,
              cell: (e) => {
                const r = ranges.get(e.id)
                if (!r) return <Text size="sm" c="dimmed">–</Text>
                return (
                  <Group gap={6}>
                    <Text size="sm" ff="monospace">{r.firewalls.join(', ')}</Text>
                    <Badge size="sm" variant="light" color={ROUTE_TONE[r.state]}>{t(`firewalls.route.${r.state}`)}</Badge>
                  </Group>
                )
              } },
            { id: 'source', header: t('ipam.col.source'), hideOnPhone: true, cell: sources },
          ]} />
      )}
      {adding && addType && (
        <AddEntry type={addType} onClose={() => setAdding(false)} onAdded={(id) => { setAdding(false); navigate(entryPath(addType.id, id)) }} />
      )}
    </>
  )
}
