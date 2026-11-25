import { Button, Group, Stack, Text, Title } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useFound, type FoundLink } from '@/api/inventoryFound'
import { useUnknownSenders } from '@/api/unknownSenders'
import { type DataColumn, DataTable, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { ago } from '@/lib/time'

/** One row of the Devices table: a box LLDP/CDP sees, or an address that sends (#1443). */
interface FoundRow {
  id: string; address: string; says: string; by: string; seen: number | null
  ignore: { url: string; body: Record<string, unknown> }
  start: Record<string, string>
}

/** Inventory › Discovery (issues #891, #968): what the agents found that the inventory doesn't
 *  have yet. Nothing is added on its own: each row is added or ignored by the crew. */
export function DiscoveryView({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const found = useFound()
  const senders = useUnknownSenders()
  const done = () => void qc.invalidateQueries({ queryKey: qk.inventoryAll })
  const ignore = useMutation({ mutationFn: (r: { url: string; body: Record<string, unknown> }) => post(r.url, r.body), onSuccess: done })
  const confirm = useMutation({
    mutationFn: (l: FoundLink) => post('/api/links', { a: l.a, a_port: l.a_port, b: l.b, b_port: l.b_port, ...(l.speed ? { speed: l.speed } : {}) }),
    onSuccess: done,
  })
  if (found.isPending && senders.isPending) return <LoadingState rows={4} />

  const rows: FoundRow[] = [
    ...(found.data?.devices ?? []).map((d): FoundRow => ({
      id: `n:${d.name}`, address: '–',
      says: d.protocol ? t('inventoryFound.saysProtocol', { name: d.name, protocol: d.protocol.toUpperCase() }) : d.name,
      by: d.seen_by.map((s) => t('inventoryFound.seenOn', { protocol: (d.protocol || 'LLDP').toUpperCase(), switch: s.switch, port: s.port })).join(', '),
      seen: null, ignore: { url: '/api/inventory/found/ignore', body: { kind: 'device', key: d.name } },
      start: { name: d.name.split('.')[0] },
    })),
    ...(senders.data?.senders ?? []).filter((s) => !s.ignored).map((s): FoundRow => ({
      id: `s:${s.address}`, address: s.address,
      says: s.name ? t('inventoryFound.saysSends', { name: s.name, what: kinds(t, s.kinds) }) : t('inventoryFound.unknownSends', { what: kinds(t, s.kinds) }),
      by: t('inventoryFound.senders', { agents: s.agents.join(', ') || '–' }), seen: s.last,
      ignore: { url: '/api/inventory/unknown-senders/ignore', body: { address: s.address, ignored: true } },
      start: { name: s.name || s.address, mgmt_ip: s.address },
    })),
  ]
  const links = found.data?.links ?? []
  const addPath = (start: Record<string, string>) => `/inventory/devices/new?${new URLSearchParams(start).toString()}`

  const deviceColumns: DataColumn<FoundRow>[] = [
    { id: 'address', header: t('inventoryFound.address'), mono: true, sort: (r) => r.address, cell: (r) => r.address },
    { id: 'says', header: t('inventoryFound.says'), sort: (r) => r.says, cell: (r) => r.says },
    { id: 'by', header: t('inventoryFound.by'), hideOnPhone: true, cell: (r) => <Text span size="sm" c="dimmed">{r.by}</Text> },
    { id: 'seen', header: t('inventoryFound.seen'), hideOnPhone: true, sort: (r) => r.seen ?? 0, descFirst: true,
      cell: (r) => <Text span size="sm" c="dimmed">{r.seen ? ago(r.seen) : t('inventoryFound.now')}</Text> },
    ...(canEdit ? [{ id: 'actions', header: t('inventoryFound.actions'), cell: (r: FoundRow) => (
      <Group gap={4} justify="flex-end" wrap="nowrap">
        <Button size="xs" variant="default" onClick={() => navigate(addPath(r.start))}>{t('inventoryFound.add')}</Button>
        <Button size="xs" variant="subtle" color="gray" loading={ignore.isPending && ignore.variables === r.ignore}
          onClick={() => ignore.mutate(r.ignore)}>{t('inventoryFound.ignore')}</Button>
      </Group>
    ) }] : []),
  ]
  const linkColumns: DataColumn<FoundLink>[] = [
    { id: 'a', header: t('inventoryFound.from'), mono: true, sort: (l) => l.a, cell: (l) => `${l.a} ${l.a_port}` },
    { id: 'b', header: t('inventoryFound.to'), mono: true, sort: (l) => l.b, cell: (l) => `${l.b} ${l.b_port}` },
    { id: 'by', header: t('inventoryFound.seenBy'), hideOnPhone: true, cell: (l) => <Text span size="sm" c="dimmed">{(l.protocol || 'LLDP').toUpperCase()}</Text> },
    { id: 'speed', header: t('inventoryFound.speed'), mono: true, cell: (l) => (l.speed ? `${l.speed}G` : '–') },
    ...(canEdit ? [{ id: 'actions', header: t('inventoryFound.actions'), cell: (l: FoundLink) => (
      <Group gap={4} justify="flex-end" wrap="nowrap">
        <Button size="xs" variant="default" loading={confirm.isPending && confirm.variables === l} onClick={() => confirm.mutate(l)}>{t('inventoryFound.confirm')}</Button>
        <Button size="xs" variant="subtle" color="gray" onClick={() => ignore.mutate({ url: '/api/inventory/found/ignore', body: { kind: 'link', key: l.key } })}>
          {t('inventoryFound.ignore')}
        </Button>
      </Group>
    ) }] : []),
  ]
  const error = (found.error ?? senders.error ?? ignore.error ?? confirm.error) as Error | null
  return (
    <Stack gap="lg">
      <Text c="dimmed">{t('inventoryFound.intro')}</Text>
      {error && <ErrorBanner error={error} />}
      <Stack gap="xs">
        <Title order={2} size="h4">{t('inventoryFound.devices')} <Text span c="dimmed" fw={400}>{rows.length}</Text></Title>
        <DataTable rows={rows} columns={deviceColumns} rowKey={(r) => r.id} label={t('inventoryFound.devices')} minWidth={760}
          empty={t('inventoryFound.noDevices')} />
      </Stack>
      <Stack gap="xs">
        <Title order={2} size="h4">{t('inventoryFound.links')} <Text span c="dimmed" fw={400}>{links.length}</Text></Title>
        <DataTable rows={links} columns={linkColumns} rowKey={(l) => l.key} label={t('inventoryFound.links')} minWidth={760}
          empty={t('inventoryFound.noLinks')} />
        <Text size="xs" c="dimmed">{t('inventoryFound.dashed')}</Text>
      </Stack>
      {!!(found.data?.ignored.devices || found.data?.ignored.links) && (
        <Text size="xs" c="dimmed">{t('inventoryFound.ignoredCount', { devices: found.data.ignored.devices, links: found.data.ignored.links })}</Text>
      )}
    </Stack>
  )
}

/** "syslog, traps": what an unknown sender sent. */
function kinds(t: (k: string) => string, k: Partial<Record<string, number>>) {
  return Object.keys(k).filter((x) => k[x]).map((x) => t(`inventoryFound.kind.${x}`)).join(', ')
}

