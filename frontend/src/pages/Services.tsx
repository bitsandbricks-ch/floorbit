import {
  Alert, Button, Drawer, Group, Menu, Modal, NumberInput, Paper, Select, SimpleGrid, Stack, Text, TextInput,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, useHealth } from '@/api/queries'
import type { OwnCheck } from '@/api/serviceChecks'
import type {
  DnsResolver, GameServer, GameServerList, InternetSite, IspUplink, Services as ServicesData, ServiceStatus, ServiceSummary,
} from '@/api/types'
import { Layout } from '@/components/Layout'
import { ConfirmButton, ErrorBanner, FilterBar, LoadingState, PageHead, StatGrid, StatTile, useFilters } from '@bitsandbricks/ui'
import { ServiceGroup } from '@/widgets/ServiceList'
import { STATES, TYPES, serviceRows, typeOfKind } from '@/widgets/serviceRows'
import type { ServiceRowData, ServiceType } from '@/widgets/serviceRows'
import { EntitySelect } from '@/components/EntitySelect'
import { RconConsole, ServerModal } from './services/GameServerParts'
import { CheckModal } from './services/CheckModal'
import { ServicePanel } from './services/ServicePanel'
import './services/Services.css'


type Editing = { kind: 'uplinks'; item: IspUplink | null } | { kind: 'resolvers'; item: DnsResolver | null }
  | { kind: 'sites'; item: InternetSite | null } | { kind: 'game'; item: GameServer | null }
  | { kind: 'checks'; item: OwnCheck | null } | null

const NO_TAG = '\u0000'

/** Every service the event depends on (issues #471, #889), with what the Service health page showed
 *  (#1337): one list grouped by type, tag or state, one "Add service", one "Check now", and a panel
 *  with a service's numbers, tags and mute next to the list. */
export default function Services() {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const canSetUp = useCan('settings.manage')
  const canRcon = useCan('games.rcon')
  const canMute = useCan('incidents.work')
  const q = useQuery({ queryKey: qk.services, queryFn: () => get<ServicesData>('/api/services'), refetchInterval: 15_000 })
  const games = useQuery({ queryKey: qk.gameServers, queryFn: () => get<GameServerList>('/api/game-servers'), refetchInterval: 15_000 })
  const summary = useQuery({ queryKey: qk.serviceSummary, queryFn: () => get<ServiceSummary>('/api/services/summary'), refetchInterval: 15_000 })
  const health = useHealth()
  const [editing, setEditing] = useState<Editing>(null)
  const [console_, setConsole] = useState<GameServer | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const wide = useMediaQuery('(min-width: 75em)', true, { getInitialValueInEffect: false })
  const filters = useFilters({ shown: 'all', by: 'type' })
  const { search } = filters
  const shown = filters.values.shown as 'all' | 'notUp' | 'up'
  const by = filters.values.by as 'type' | 'tag' | 'state'
  const data = q.data
  const qc = useQueryClient()
  const check = useMutation({
    mutationFn: () => post<ServicesData>('/api/services/check', {}),
    onSuccess: (fresh) => {
      qc.setQueryData(qk.services, fresh)
      void qc.invalidateQueries({ queryKey: qk.serviceSummary })
      void qc.invalidateQueries({ queryKey: qk.health })
      void qc.invalidateQueries({ queryKey: qk.gameServers })
    },
  })
  const common = useMutation({
    mutationFn: () => post<ServicesData>('/api/services/sites/common', {}),
    onSuccess: (fresh) => qc.setQueryData(qk.services, fresh),
  })
  useLiveEvent('health.changed', () => void qc.invalidateQueries({ queryKey: qk.health }))
  const tags = summary.data?.tags ?? {}
  const own = serviceRows(t, data, games.data, {
    uplink: canEdit ? (u) => setEditing({ kind: 'uplinks', item: u }) : undefined,
    dns: canEdit ? (r) => setEditing({ kind: 'resolvers', item: r }) : undefined,
    site: canEdit ? (s) => setEditing({ kind: 'sites', item: s }) : undefined,
    game: canSetUp ? (g) => setEditing({ kind: 'game', item: g }) : undefined,
    check: canEdit ? (c) => setEditing({ kind: 'checks', item: c }) : undefined,
  })
  const ownIds = new Set(own.map((r) => r.sid))
  const ownTypes = new Set(own.map((r) => r.type))
  // What plugins and other pages watch (DHCP, firewalls, an HTTP check plugin, ...): listed from the
  // shared summary (#1037), so this page counts what the dashboards count and nothing is only on one.
  const elsewhere: ServiceRowData[] = (summary.data?.rows ?? [])
    .filter((r) => !ownIds.has(r.id) && r.id !== 'sites' && !r.id.startsWith('site:'))
    // The event has one LAN cache: the page's own row already shows it, with more numbers (#1419).
    .filter((r) => !(typeOfKind(r.kind) === 'lancache' && ownTypes.has('lancache')))
    .map((r) => ({
      key: `h-${r.id}`, sid: r.id, type: typeOfKind(r.kind), name: r.name, status: r.status, target: r.summary,
      value: null, unit: null, note: null, points: [],
      elsewhere: t(`services.setUpElsewhere.${r.kind === 'firewall' || r.kind === 'dhcp' ? r.kind : 'other'}`),
    }))
  const rows = [...own, ...elsewhere].map((r) => ({ ...r, tags: tags[r.sid] ?? [] }))
  const allTags = [...new Set(rows.flatMap((r) => r.tags))].sort((x, y) => x.localeCompare(y))
  const needle = search.trim().toLowerCase()
  const matching = rows.filter((r) => (shown === 'all' || (shown === 'up') === (r.status === 'up'))
    && (!needle || `${r.name} ${r.target} ${t(`services.types.${r.type}`)} ${r.tags.join(' ')}`.toLowerCase().includes(needle)))
  const groups = by === 'type'
    ? TYPES.map((k) => ({ id: k, title: t(`services.groups.${k}`), rows: matching.filter((r) => r.type === k) }))
    : by === 'tag'
      // A service with two tags shows under both; one without under "No tag".
      ? [...allTags, NO_TAG].map((tag) => ({ id: `tag-${tag}`, title: tag === NO_TAG ? t('services.noTag') : tag,
        rows: matching.filter((r) => (tag === NO_TAG ? !r.tags.length : r.tags.includes(tag))) }))
      : STATES.map((k) => ({ id: k, title: t(`services.status.${k}`), rows: matching.filter((r) => r.status === k) }))
  const count = (s: ServiceStatus) => rows.filter((r) => r.status === s).length
  const notUp = rows.length - count('up')
  const adds = [
    canEdit && { type: 'uplink', open: () => setEditing({ kind: 'uplinks', item: null }) },
    canEdit && { type: 'dns', open: () => setEditing({ kind: 'resolvers', item: null }) },
    canEdit && { type: 'site', open: () => setEditing({ kind: 'sites', item: null }) },
    canSetUp && { type: 'game', open: () => setEditing({ kind: 'game', item: null }) },
    canEdit && { type: 'check', open: () => setEditing({ kind: 'checks', item: null }) },
  ].filter(Boolean) as { type: ServiceType; open: () => void }[]
  const loaded = !!data && !!games.data
  const picked = rows.find((r) => r.key === selected) ?? null
  const panel = picked && (
    <ServicePanel row={picked} check={health.data?.checks.find((c) => c.id === picked.sid)} allTags={allTags}
      canEdit={canEdit} canMute={canMute} canRcon={canRcon} onConsole={() => picked.game && setConsole(picked.game)}
      onClose={() => setSelected(null)} />
  )
  return (
    <Layout title={t('services.title')}>
      <PageHead title={t('services.title')} desc={t('services.intro')}
        actions={(
          <>
            {canEdit && rows.length > 0 && <Button variant="default" loading={check.isPending} onClick={() => check.mutate()}>{t('services.checkNow')}</Button>}
            {adds.length > 0 && (
              <Menu position="bottom-end">
                <Menu.Target><Button leftSection={<IconPlus size={16} />}>{t('services.add')}</Button></Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>{t('services.addWhich')}</Menu.Label>
                  {adds.map((a) => <Menu.Item key={a.type} onClick={a.open}>{t(`services.types.${a.type}`)}</Menu.Item>)}
                </Menu.Dropdown>
              </Menu>
            )}
          </>
        )} />
      <Stack gap="lg">
        <ErrorBanner error={q.error ?? games.error} onRetry={() => { void q.refetch(); void games.refetch() }} />
        {rows.length > 0 && (
          <StatGrid columns={4}>
            <StatTile label={t('services.count.down')} value={String(count('down'))} tone={count('down') ? 'err' : undefined} />
            <StatTile label={t('services.count.warn')} value={String(count('warn'))} tone={count('warn') ? 'warn' : undefined} />
            <StatTile label={t('services.count.up')} value={String(count('up'))} tone={count('up') ? 'ok' : undefined} />
            <StatTile label={t('services.count.all')} value={String(rows.length)}
              sub={count('unknown') ? t('services.count.unknown', { count: count('unknown') }) : undefined} />
          </StatGrid>
        )}
        {!loaded && !q.error && !games.error && <LoadingState />}
        {loaded && rows.length === 0 && (
          <Paper withBorder p="md">
            <Stack gap="xs" align="flex-start">
              <Text c="dimmed">{t(adds.length ? 'services.emptyAdmin' : 'services.empty')}</Text>
              {canEdit && (
                <Button size="compact-md" variant="default" loading={common.isPending} onClick={() => common.mutate()}>{t('services.addCommon')}</Button>
              )}
            </Stack>
          </Paper>
        )}
        {common.error && <Alert color="down" role="alert">{common.error.message}</Alert>}
        {check.error && <Alert color="down" role="alert">{check.error.message}</Alert>}
        {rows.length > 0 && (
          <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('services.search')} onClear={filters.clear}
            groups={filters.groups([
              { key: 'shown', label: t('services.show'), options: [
                { value: 'all', label: t('services.filter.all'), count: rows.length },
                { value: 'notUp', label: t('services.filter.notUp'), count: notUp },
                { value: 'up', label: t('services.filter.up'), count: rows.length - notUp },
              ] },
              { key: 'by', label: t('services.groupBy'), options: [
                { value: 'type', label: t('services.byType') }, { value: 'tag', label: t('services.byTag') },
                { value: 'state', label: t('services.byState') },
              ] },
            ])} />
        )}
        {rows.length > 0 && matching.length === 0 && <Text c="dimmed">{t('services.noMatch')}</Text>}
        <div className="fb-services-split">
          <Stack gap="lg" className="fb-services-list">
            {groups.filter((g) => g.rows.length).map((g) => (
              <ServiceGroup key={g.id} title={g.title} rows={g.rows} showType={by !== 'type'} canRcon={canRcon} onConsole={setConsole}
                onSelect={(r) => setSelected(selected === r.key ? null : r.key)} selected={selected} />
            ))}
          </Stack>
          {wide && panel}
        </div>
        {(data?.via_agent || games.data?.via_agent) && <Text size="sm" c="dimmed">{t('services.viaAgent')}</Text>}
        {data && !data.lan_cache && rows.length > 0 && <Text size="sm" c="dimmed">{t('services.noLanCache')}</Text>}
      </Stack>
      {!wide && <Drawer opened={!!panel} onClose={() => setSelected(null)} position="right" size="md" withCloseButton={false} padding={0}>{panel}</Drawer>}
      {editing?.kind === 'uplinks' && data && <UplinkModal uplink={editing.item} ports={data.probe_ports} devices={data.devices} onClose={() => setEditing(null)} />}
      {editing?.kind === 'resolvers' && <ResolverModal resolver={editing.item} onClose={() => setEditing(null)} />}
      {editing?.kind === 'sites' && data && <SiteModal site={editing.item} ports={data.probe_ports} onClose={() => setEditing(null)} />}
      {editing?.kind === 'game' && <ServerModal server={editing.item} onClose={() => setEditing(null)} />}
      {editing?.kind === 'checks' && <CheckModal check={editing.item} onClose={() => setEditing(null)} />}
      {console_ && <RconConsole server={console_} onClose={() => setConsole(null)} />}
    </Layout>
  )
}

function useSave(kind: 'uplinks' | 'resolvers' | 'sites', id: string | undefined, onClose: () => void) {
  const qc = useQueryClient()
  const done = () => { void qc.invalidateQueries({ queryKey: qk.services }); onClose() }
  const save = useMutation({
    mutationFn: (body: object) => (id ? put(`/api/services/${kind}/${id}`, body) : post(`/api/services/${kind}`, body)),
    onSuccess: done,
  })
  const remove = useMutation({ mutationFn: () => del(`/api/services/${kind}/${id}`), onSuccess: done })
  return { save, remove }
}

function ModalFoot({ id, pending, disabled, onSave, onRemove, question }: {
  id?: string; pending: boolean; disabled: boolean; onSave: () => void; onRemove: () => void; question: string
}) {
  const { t } = useTranslation()
  return (
    <Group justify={id ? 'space-between' : 'flex-end'}>
      {id && <ConfirmButton variant="subtle" danger label={t('services.remove')} question={question} onConfirm={onRemove} />}
      <Button loading={pending} disabled={disabled} onClick={onSave}>{t('services.save')}</Button>
    </Group>
  )
}

function UplinkModal({ uplink, ports, devices, onClose }: { uplink: IspUplink | null; ports: number[]; devices: string[]; onClose: () => void }) {
  const { t } = useTranslation()
  const [form, setForm] = useState({
    name: uplink?.name ?? '', device: uplink?.device ?? '', port: uplink?.port ?? '',
    capacity_mbps: uplink?.capacity_mbps ?? 1000, probe_host: uplink?.probe_host ?? '', probe_port: String(uplink?.probe_port ?? 443),
  })
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const { save, remove } = useSave('uplinks', uplink?.id, onClose)
  const error = save.error ?? remove.error
  return (
    <Modal opened onClose={onClose} title={uplink ? t('services.editUplink') : t('services.addUplink')}>
      <Stack gap="sm">
        <TextInput label={t('services.name')} placeholder={t('services.uplinkPlaceholder')} value={form.name} onChange={(e) => set({ name: e.currentTarget.value })} />
        <SimpleGrid cols={2} spacing="sm">
          <Select label={t('services.device')} placeholder="core-01" data={devices} searchable value={form.device || null}
            onChange={(v) => set({ device: v ?? '', port: v === form.device ? form.port : '' })} />
          <EntitySelect kind="ports" label={t('services.port')} switchName={form.device} showUsed value={form.port}
            onChange={(v) => set({ port: v })} />
        </SimpleGrid>
        <NumberInput label={t('services.capacity')} min={1} max={400000} value={form.capacity_mbps}
          onChange={(v) => set({ capacity_mbps: typeof v === 'number' ? v : 0 })} />
        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
          <TextInput label={t('services.probeHost')} description={t('services.probeHelp')} placeholder="www.example.com"
            value={form.probe_host} onChange={(e) => set({ probe_host: e.currentTarget.value })} />
          <Select label={t('services.probePort')} data={ports.map(String)} value={form.probe_port} allowDeselect={false}
            onChange={(v) => set({ probe_port: v ?? '443' })} />
        </SimpleGrid>
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
        <ModalFoot id={uplink?.id} pending={save.isPending} disabled={!form.name.trim() || !form.device.trim() || !form.port.trim()}
          onSave={() => save.mutate({ ...form, probe_port: Number(form.probe_port) })} onRemove={() => remove.mutate()}
          question={t('services.removeQuestion', { name: uplink?.name ?? '' })} />
      </Stack>
    </Modal>
  )
}

function ResolverModal({ resolver, onClose }: { resolver: DnsResolver | null; onClose: () => void }) {
  const { t } = useTranslation()
  const [form, setForm] = useState({ name: resolver?.name ?? '', address: resolver?.address ?? '', lookup: resolver?.lookup ?? '' })
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const { save, remove } = useSave('resolvers', resolver?.id, onClose)
  const error = save.error ?? remove.error
  return (
    <Modal opened onClose={onClose} title={resolver ? t('services.editResolver') : t('services.addResolver')}>
      <Stack gap="sm">
        <TextInput label={t('services.name')} placeholder={t('services.resolverPlaceholder')} value={form.name} onChange={(e) => set({ name: e.currentTarget.value })} />
        <TextInput label={t('services.address')} placeholder="192.0.2.53" value={form.address} onChange={(e) => set({ address: e.currentTarget.value })} />
        <TextInput label={t('services.lookup')} description={t('services.lookupHelp')} placeholder="example.com" value={form.lookup}
          onChange={(e) => set({ lookup: e.currentTarget.value })} />
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
        <ModalFoot id={resolver?.id} pending={save.isPending} disabled={!form.name.trim() || !form.address.trim() || !form.lookup.trim()}
          onSave={() => save.mutate(form)} onRemove={() => remove.mutate()} question={t('services.removeQuestion', { name: resolver?.name ?? '' })} />
      </Stack>
    </Modal>
  )
}

function SiteModal({ site, ports, onClose }: { site: InternetSite | null; ports: number[]; onClose: () => void }) {
  const { t } = useTranslation()
  const [form, setForm] = useState({ name: site?.name ?? '', host: site?.host ?? '', port: String(site?.port ?? 443) })
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const { save, remove } = useSave('sites', site?.id, onClose)
  const error = save.error ?? remove.error
  return (
    <Modal opened onClose={onClose} title={site ? t('services.editSite') : t('services.addSite')}>
      <Stack gap="sm">
        <TextInput label={t('services.name')} placeholder={t('services.sitePlaceholder')} value={form.name} onChange={(e) => set({ name: e.currentTarget.value })} />
        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
          <TextInput label={t('services.host')} description={t('services.hostHelp')} placeholder="www.example.com" value={form.host}
            onChange={(e) => set({ host: e.currentTarget.value })} />
          <Select label={t('services.probePort')} data={ports.map(String)} value={form.port} allowDeselect={false}
            onChange={(v) => set({ port: v ?? '443' })} />
        </SimpleGrid>
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
        <ModalFoot id={site?.id} pending={save.isPending} disabled={!form.name.trim() || !form.host.trim()}
          onSave={() => save.mutate({ ...form, port: Number(form.port) })} onRemove={() => remove.mutate()}
          question={t('services.removeQuestion', { name: site?.name ?? '' })} />
      </Stack>
    </Modal>
  )
}
