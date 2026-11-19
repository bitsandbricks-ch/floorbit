import {
  Alert, Badge, Button, Group, Menu, Modal, NumberInput, Paper, Progress, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { IconPlus, IconSearch } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type {
  DnsResolver, GameServer, GameServerList, InternetSite, IspUplink, LanCacheState, ServiceStatus, Services as ServicesData,
} from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { Sparkline } from '@/widgets/Sparkline'
import { bps } from './stats/format'
import { bytes } from './traffic/format'
import { EntitySelect } from '@/components/EntitySelect'
import { RconConsole, ServerModal } from './services/GameServerParts'

const TONE: Record<ServiceStatus, string> = { up: 'up', warn: 'warn', down: 'down', unknown: 'gray' }
const BIT: Record<ServiceStatus, string> = { up: '', warn: 'is-warn', down: 'is-down', unknown: 'is-off' }

type Editing = { kind: 'uplinks'; item: IspUplink | null } | { kind: 'resolvers'; item: DnsResolver | null }
  | { kind: 'sites'; item: InternetSite | null } | { kind: 'game'; item: GameServer | null } | null

/** Every kind of service, in the order the page groups them. The LAN cache comes from its log
 *  or plugin, so nobody adds one here. */
const TYPES = ['uplink', 'dns', 'site', 'lancache', 'game'] as const
type ServiceType = typeof TYPES[number]
const STATES: ServiceStatus[] = ['down', 'warn', 'unknown', 'up']

/** One row of the list, whatever kind of service it is. */
interface Row {
  key: string; type: ServiceType; name: string; status: ServiceStatus; target: string
  value: string | null; unit: string | null; note: string | null; points: number[]
  edit?: () => void; game?: GameServer
}

/** Internet lines, DNS resolvers, the sites players need, the LAN cache and the game servers
 *  (issues #471, #472, #889): one list, grouped by type or state, with one "Add service". */
export default function Services() {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const canSetUp = useCan('settings.manage')
  const canRcon = useCan('games.rcon')
  const q = useQuery({ queryKey: qk.services, queryFn: () => get<ServicesData>('/api/services'), refetchInterval: 15_000 })
  const games = useQuery({ queryKey: qk.gameServers, queryFn: () => get<GameServerList>('/api/game-servers'), refetchInterval: 15_000 })
  const [editing, setEditing] = useState<Editing>(null)
  const [console_, setConsole] = useState<GameServer | null>(null)
  const [search, setSearch] = useState('')
  const [shown, setShown] = useState<'all' | 'notUp' | 'up'>('all')
  const [by, setBy] = useState<'type' | 'state'>('type')
  const data = q.data
  const qc = useQueryClient()
  const check = useMutation({
    mutationFn: () => post<ServicesData>('/api/services/check', {}),
    onSuccess: (fresh) => qc.setQueryData(qk.services, fresh),
  })
  const common = useMutation({
    mutationFn: () => post<ServicesData>('/api/services/sites/common', {}),
    onSuccess: (fresh) => qc.setQueryData(qk.services, fresh),
  })
  const rows = toRows(t, data, games.data, {
    uplink: canEdit ? (u) => setEditing({ kind: 'uplinks', item: u }) : undefined,
    dns: canEdit ? (r) => setEditing({ kind: 'resolvers', item: r }) : undefined,
    site: canEdit ? (s) => setEditing({ kind: 'sites', item: s }) : undefined,
    game: canSetUp ? (g) => setEditing({ kind: 'game', item: g }) : undefined,
  })
  const needle = search.trim().toLowerCase()
  const matching = rows.filter((r) => (shown === 'all' || (shown === 'up') === (r.status === 'up'))
    && (!needle || `${r.name} ${r.target} ${t(`services.types.${r.type}`)}`.toLowerCase().includes(needle)))
  const groups = by === 'type'
    ? TYPES.map((k) => ({ id: k, title: t(`services.groups.${k}`), rows: matching.filter((r) => r.type === k) }))
    : STATES.map((k) => ({ id: k, title: t(`services.status.${k}`), rows: matching.filter((r) => r.status === k) }))
  const notUp = rows.filter((r) => r.status !== 'up').length
  const adds = [
    canEdit && { type: 'uplink', open: () => setEditing({ kind: 'uplinks', item: null }) },
    canEdit && { type: 'dns', open: () => setEditing({ kind: 'resolvers', item: null }) },
    canEdit && { type: 'site', open: () => setEditing({ kind: 'sites', item: null }) },
    canSetUp && { type: 'game', open: () => setEditing({ kind: 'game', item: null }) },
  ].filter(Boolean) as { type: ServiceType; open: () => void }[]
  const loaded = !!data && !!games.data
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
        {(q.error || games.error) && <Alert color="down" role="alert">{(q.error || games.error)!.message}</Alert>}
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
        {rows.length > 0 && (
          <Group gap="sm" wrap="wrap">
            <TextInput leftSection={<IconSearch size={16} />} placeholder={t('services.search')} aria-label={t('services.search')}
              value={search} onChange={(e) => setSearch(e.currentTarget.value)} style={{ flex: '1 1 220px', maxWidth: 360 }} />
            <SegmentedControl value={shown} onChange={(v) => setShown(v as typeof shown)} aria-label={t('services.show')} data={[
              { value: 'all', label: t('services.filter.all', { count: rows.length }) },
              { value: 'notUp', label: t('services.filter.notUp', { count: notUp }) },
              { value: 'up', label: t('services.filter.up', { count: rows.length - notUp }) },
            ]} />
            <Select aria-label={t('services.groupBy')} w={170} allowDeselect={false} value={by} onChange={(v) => setBy((v ?? 'type') as typeof by)}
              data={[{ value: 'type', label: t('services.byType') }, { value: 'state', label: t('services.byState') }]} />
          </Group>
        )}
        {rows.length > 0 && matching.length === 0 && <Text c="dimmed">{t('services.noMatch')}</Text>}
        {groups.filter((g) => g.rows.length).map((g) => (
          <Stack key={g.id} gap="xs" component="section" aria-label={g.title}>
            <Group gap="xs">
              <Title order={2} size="h4">{g.title}</Title>
              <Badge variant="default" radius="sm">{g.rows.length}</Badge>
            </Group>
            <Paper withBorder className="fb-service-list">
              {g.rows.map((r) => (
                <ServiceRow key={r.key} row={r} showType={by === 'state'} canRcon={canRcon} onConsole={() => r.game && setConsole(r.game)} />
              ))}
            </Paper>
          </Stack>
        ))}
        {(data?.via_agent || games.data?.via_agent) && <Text size="sm" c="dimmed">{t('services.viaAgent')}</Text>}
        {data && !data.lan_cache && rows.length > 0 && <Text size="sm" c="dimmed">{t('services.noLanCache')}</Text>}
      </Stack>
      {editing?.kind === 'uplinks' && data && <UplinkModal uplink={editing.item} ports={data.probe_ports} devices={data.devices} onClose={() => setEditing(null)} />}
      {editing?.kind === 'resolvers' && <ResolverModal resolver={editing.item} onClose={() => setEditing(null)} />}
      {editing?.kind === 'sites' && data && <SiteModal site={editing.item} ports={data.probe_ports} onClose={() => setEditing(null)} />}
      {editing?.kind === 'game' && <ServerModal server={editing.item} onClose={() => setEditing(null)} />}
      {console_ && <RconConsole server={console_} onClose={() => setConsole(null)} />}
    </Layout>
  )
}

type T = (key: string, opts?: Record<string, unknown>) => string

/** The page's rows from the two lists: the headline number, a line under it and the sparkline. */
function toRows(t: T, d: ServicesData | undefined, g: GameServerList | undefined, edit: {
  uplink?: (u: IspUplink) => void; dns?: (r: DnsResolver) => void; site?: (s: InternetSite) => void; game?: (s: GameServer) => void
}): Row[] {
  const failed = (status: ServiceStatus, error: string) => (status === 'down' || status === 'unknown' ? error || t('services.notChecked') : null)
  const rows: Row[] = []
  for (const u of d?.uplinks ?? []) {
    const portDown = u.port_state === 'down' || u.port_state === 'disabled'
    const used = portDown ? null : u.utilization ?? null
    rows.push({
      key: `u-${u.id}`, type: 'uplink', name: u.name, status: u.status, target: `${u.device} ${u.port} · ${bps(u.capacity_mbps * 1e6)}`,
      value: used != null ? `${Math.round(used * 100)}%` : null, unit: used != null ? t('services.used') : null,
      note: portDown ? t('services.portDown') : [
        used != null && t('services.inOut', { in: bps(u.in_bps), out: bps(u.out_bps) }),
        u.latency_ms != null && t('services.latency', { ms: u.latency_ms }),
        u.loss != null && t('services.loss', { pct: Math.round(u.loss * 100) }),
      ].filter(Boolean).join(' · ') || u.error || null,
      points: u.history.map(([, ms]) => ms ?? 0), edit: edit.uplink && (() => edit.uplink!(u)),
    })
  }
  for (const r of d?.resolvers ?? []) {
    const ok = r.status === 'up' || r.status === 'warn'
    rows.push({
      key: `r-${r.id}`, type: 'dns', name: r.name, status: r.status, target: `${r.address} · ${r.lookup}`,
      value: ok ? `${r.latency_ms} ms` : null, unit: null,
      note: ok ? t('services.answers', { count: r.answers ?? 0 }) : failed(r.status, r.error),
      points: r.history.map(([, ms]) => ms ?? 0), edit: edit.dns && (() => edit.dns!(r)),
    })
  }
  for (const s of d?.sites ?? []) {
    const ok = s.status === 'up' || s.status === 'warn'
    rows.push({
      key: `s-${s.id}`, type: 'site', name: s.name, status: s.status, target: s.port === 443 ? s.host : `${s.host}:${s.port}`,
      value: ok ? `${s.latency_ms} ms` : null, unit: null,
      note: ok ? (s.loss ? t('services.loss', { pct: Math.round(s.loss * 100) }) : null) : failed(s.status, s.error),
      points: s.history.map(([, ms]) => ms ?? 0), edit: edit.site && (() => edit.site!(s)),
    })
  }
  const c = d?.lan_cache
  if (c) {
    rows.push({
      key: 'lancache', type: 'lancache', name: t('services.lanCache'), status: c.status, target: c.demo ? t('services.demo') : t('services.thisHour'),
      value: c.hit_ratio != null ? `${Math.round(c.hit_ratio * 100)}%` : null, unit: t('services.fromDisk'),
      note: [t('services.served', { bytes: bytes(c.served_bytes), rate: bps(c.bps) }),
        c.disk && t('services.diskUsed', { used: bytes(c.disk.used), total: bytes(c.disk.total) }), c.error].filter(Boolean).join(' · '),
      points: [],
    })
  }
  for (const s of g?.servers ?? []) {
    const info = s.status === 'up' ? s.info : null
    rows.push({
      key: `g-${s.id}`, type: 'game', name: s.name, status: s.status, target: [s.game || s.info?.game, `${s.host}:${s.port}`].filter(Boolean).join(' · '),
      value: info && s.query !== 'tcp' ? `${info.players}/${info.max_players}` : null, unit: info && s.query !== 'tcp' ? t('gameServers.players') : null,
      note: info ? [info.map && t('gameServers.map', { map: info.map }), info.ping_ms != null && `${info.ping_ms} ms`, info.version].filter(Boolean).join(' · ')
        : s.error || t('gameServers.notAsked'),
      points: s.query !== 'tcp' ? s.history.map(([, n]) => n ?? 0) : [], edit: edit.game && (() => edit.game!(s)), game: s,
    })
  }
  return rows
}

/** One service on one line: state, name and where it is, the number that matters, its recent
 *  history and what can be done with it. */
function ServiceRow({ row: r, showType, canRcon, onConsole }: { row: Row; showType: boolean; canRcon: boolean; onConsole: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  // Ask this one game server now instead of waiting for the next poll (after a restart, say).
  const check = useMutation({
    mutationFn: () => post(`/api/game-servers/check/${r.game!.id}`, {}),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.gameServers }),
  })
  const bad = r.status === 'down' || r.status === 'unknown'
  return (
    <div className="fb-service-row" role="group" aria-label={r.name} data-status={r.status}>
      <div className="fb-service-name">
        <span className={`fb-bit ${BIT[r.status]}`} aria-hidden="true" />
        <div style={{ minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            <Text fw={600} truncate>{r.name}</Text>
            <Badge size="sm" variant="light" color={TONE[r.status]}>{t(`services.status.${r.status}`)}</Badge>
          </Group>
          <Text size="sm" c="dimmed" ff="monospace" truncate>{showType ? `${t(`services.types.${r.type}`)} · ${r.target}` : r.target}</Text>
        </div>
      </div>
      <div className="fb-service-value">
        {r.value && (
          <Group gap={6} align="baseline" wrap="nowrap">
            <Text fw={700} fz="xl" lh={1}>{r.value}</Text>
            {r.unit && <Text size="sm" c="dimmed">{r.unit}</Text>}
          </Group>
        )}
        {r.note && <Text size="sm" c={bad ? 'down' : r.status === 'warn' && !r.value ? 'warn' : undefined} lineClamp={2}>{r.note}</Text>}
      </div>
      <div className="fb-service-spark">{r.points.length > 1 && <Sparkline points={r.points} min={0} />}</div>
      <Group gap={4} className="fb-service-actions" wrap="nowrap" justify="flex-end">
        {r.game && canRcon && (
          <>
            <Button size="compact-sm" variant="default" disabled={!r.game.rcon} onClick={onConsole}
              title={r.game.rcon ? undefined : t('gameServers.noRcon')}>{t('gameServers.console')}</Button>
            <Button size="compact-sm" variant="subtle" loading={check.isPending} onClick={() => check.mutate()}>{t('gameServers.checkNow')}</Button>
          </>
        )}
        {r.edit && <Button size="compact-sm" variant="subtle" onClick={r.edit}>{t('services.edit')}</Button>}
      </Group>
    </div>
  )
}

function Card({ name, status, sub, mono = true, onEdit, children }: {
  name: string; status: ServiceStatus; sub: string; mono?: boolean; onEdit?: () => void; children: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md" component="section" aria-label={name}>
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Title order={3} size="h4" style={{ overflowWrap: 'anywhere' }}>{name}</Title>
          <Badge color={TONE[status]} variant="light">{t(`services.status.${status}`)}</Badge>
        </Group>
        <Text size="sm" c="dimmed" ff={mono ? 'monospace' : undefined} style={{ overflowWrap: 'anywhere' }}>{sub}</Text>
        {children}
        {onEdit && <Group mt={4}><Button size="compact-sm" variant="subtle" onClick={onEdit}>{t('services.edit')}</Button></Group>}
      </Stack>
    </Paper>
  )
}

function latencyPoints(history: [number, number | null][]) {
  return history.map(([, ms]) => ms ?? 0)
}

export function UplinkCard({ uplink: u, onEdit }: { uplink: IspUplink; onEdit?: () => void }) {
  const { t } = useTranslation()
  const cap = u.capacity_mbps * 1e6
  const used = u.utilization ?? null
  const points = latencyPoints(u.history)
  return (
    <Card name={u.name} status={u.status} sub={`${u.device} ${u.port} · ${bps(cap)}`} onEdit={onEdit}>
      {u.port_state === 'down' || u.port_state === 'disabled'
        ? <Text size="sm" c="down">{t('services.portDown')}</Text>
        : used !== null && (
          <>
            <Group gap="xs" align="baseline">
              <Text fw={700} fz={28} lh={1}>{Math.round(used * 100)}%</Text>
              <Text size="sm" c="dimmed">{t('services.used')}</Text>
            </Group>
            <Progress value={Math.min(100, used * 100)} color={used >= 0.8 ? 'warn' : 'up'} aria-label={t('services.used')} />
            <Text size="sm">{t('services.inOut', { in: bps(u.in_bps), out: bps(u.out_bps) })}</Text>
          </>
        )}
      {u.latency_ms != null || u.loss != null ? (
        <Text size="sm">
          {[u.latency_ms != null && t('services.latency', { ms: u.latency_ms }), u.loss != null && t('services.loss', { pct: Math.round(u.loss * 100) }),
            u.probe_host && t('services.to', { host: u.probe_host })].filter(Boolean).join(' · ')}
        </Text>
      ) : !u.probe_host && <Text size="xs" c="dimmed">{t('services.noProbe')}</Text>}
      {points.length > 1 && <div style={{ height: 30 }}><Sparkline points={points} min={0} /></div>}
      {u.error && <Text size="sm" c={u.status === 'down' ? 'down' : 'dimmed'}>{u.error}</Text>}
    </Card>
  )
}

export function ResolverCard({ resolver: r, onEdit }: { resolver: DnsResolver; onEdit?: () => void }) {
  const { t } = useTranslation()
  const points = latencyPoints(r.history)
  return (
    <Card name={r.name} status={r.status} sub={`${r.address} · ${r.lookup}`} onEdit={onEdit}>
      {r.status === 'up' || r.status === 'warn' ? (
        <Group gap="xs" align="baseline">
          <Text fw={700} fz={28} lh={1}>{r.latency_ms} ms</Text>
          <Text size="sm" c="dimmed">{t('services.answers', { count: r.answers ?? 0 })}</Text>
        </Group>
      ) : <Text size="sm" c={r.status === 'down' ? 'down' : 'dimmed'}>{r.error || t('services.notChecked')}</Text>}
      {points.length > 1 && <div style={{ height: 30 }}><Sparkline points={points} min={0} /></div>}
    </Card>
  )
}

export function SiteCard({ site: s, onEdit }: { site: InternetSite; onEdit?: () => void }) {
  const { t } = useTranslation()
  const points = latencyPoints(s.history)
  const reached = s.status === 'up' || s.status === 'warn'
  return (
    <Card name={s.name} status={s.status} sub={s.port === 443 ? s.host : `${s.host}:${s.port}`} onEdit={onEdit}>
      {reached ? (
        <Group gap="xs" align="baseline">
          <Text fw={700} fz={28} lh={1}>{s.latency_ms} ms</Text>
          {!!s.loss && <Text size="sm" c="warn">{t('services.loss', { pct: Math.round(s.loss * 100) })}</Text>}
        </Group>
      ) : <Text size="sm" c={s.status === 'down' ? 'down' : 'dimmed'}>{s.error || t('services.notChecked')}</Text>}
      {points.length > 1 && <div style={{ height: 30 }}><Sparkline points={points} min={0} /></div>}
    </Card>
  )
}

export function LanCacheCard({ cache: c }: { cache: LanCacheState }) {
  const { t } = useTranslation()
  return (
    <Card name={t('services.lanCache')} status={c.status} sub={c.demo ? t('services.demo') : t('services.thisHour')} mono={false}>
      <Group gap="xs" align="baseline">
        <Text fw={700} fz={28} lh={1}>{c.hit_ratio != null ? `${Math.round(c.hit_ratio * 100)}%` : '–'}</Text>
        <Text size="sm" c="dimmed">{t('services.fromDisk')}</Text>
      </Group>
      <Text size="sm">{t('services.served', { bytes: bytes(c.served_bytes), rate: bps(c.bps) })}</Text>
      {c.disk && (
        <>
          <Progress value={c.disk.ratio * 100} color={c.disk.ratio >= 0.9 ? 'warn' : 'up'} aria-label={t('services.disk')} />
          <Text size="sm">{t('services.diskUsed', { used: bytes(c.disk.used), total: bytes(c.disk.total) })}</Text>
        </>
      )}
      {c.error && <Text size="sm" c="warn">{c.error}</Text>}
    </Card>
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
