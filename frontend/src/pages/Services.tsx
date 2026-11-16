import {
  Alert, Badge, Button, Group, Modal, NumberInput, Paper, Progress, Select, SimpleGrid, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { DnsResolver, IspUplink, LanCacheState, ServiceStatus, Services as ServicesData } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { Sparkline } from '@/widgets/Sparkline'
import { bps } from './stats/format'
import { bytes } from './traffic/format'

const TONE: Record<ServiceStatus, string> = { up: 'up', warn: 'warn', down: 'down', unknown: 'gray' }

type Editing = { kind: 'uplinks'; item: IspUplink | null } | { kind: 'resolvers'; item: DnsResolver | null } | null

/** The internet lines, the DNS resolvers and the LAN cache (issue #471): are they up, how full,
 *  how fast. */
export default function Services() {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const q = useQuery({ queryKey: qk.services, queryFn: () => get<ServicesData>('/api/services'), refetchInterval: 15_000 })
  const [editing, setEditing] = useState<Editing>(null)
  const data = q.data
  return (
    <Layout title={t('services.title')}>
      <PageHead title={t('services.title')} desc={t('services.intro')} />
      <Stack gap="lg">
        {q.error && <Alert color="down" role="alert">{q.error.message}</Alert>}
        {data && (
          <>
            <Section title={t('services.uplinks')} add={canEdit ? () => setEditing({ kind: 'uplinks', item: null }) : undefined}
              addLabel={t('services.addUplink')} empty={data.uplinks.length === 0 ? t('services.noUplinks') : null}>
              {data.uplinks.map((u) => (
                <UplinkCard key={u.id} uplink={u} onEdit={canEdit ? () => setEditing({ kind: 'uplinks', item: u }) : undefined} />
              ))}
            </Section>
            <Section title={t('services.resolvers')} add={canEdit ? () => setEditing({ kind: 'resolvers', item: null }) : undefined}
              addLabel={t('services.addResolver')} empty={data.resolvers.length === 0 ? t('services.noResolvers') : null}>
              {data.resolvers.map((r) => (
                <ResolverCard key={r.id} resolver={r} onEdit={canEdit ? () => setEditing({ kind: 'resolvers', item: r }) : undefined} />
              ))}
            </Section>
            <Section title={t('services.lanCache')} empty={data.lan_cache ? null : t('services.noLanCache')}>
              {data.lan_cache && <LanCacheCard cache={data.lan_cache} />}
            </Section>
            {data.via_agent && <Text size="sm" c="dimmed">{t('services.viaAgent')}</Text>}
          </>
        )}
      </Stack>
      {editing?.kind === 'uplinks' && data && <UplinkModal uplink={editing.item} ports={data.probe_ports} devices={data.devices} onClose={() => setEditing(null)} />}
      {editing?.kind === 'resolvers' && <ResolverModal resolver={editing.item} onClose={() => setEditing(null)} />}
    </Layout>
  )
}

function Section({ title, add, addLabel, empty, children }: {
  title: string; add?: () => void; addLabel?: string; empty: string | null; children: React.ReactNode
}) {
  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Title order={2} size="h3">{title}</Title>
        {add && <Button size="compact-md" variant="default" onClick={add}>{addLabel}</Button>}
      </Group>
      {empty ? <Paper withBorder radius="lg" p="md"><Text c="dimmed">{empty}</Text></Paper>
        : <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">{children}</SimpleGrid>}
    </Stack>
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

function UplinkCard({ uplink: u, onEdit }: { uplink: IspUplink; onEdit?: () => void }) {
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

function ResolverCard({ resolver: r, onEdit }: { resolver: DnsResolver; onEdit?: () => void }) {
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

function LanCacheCard({ cache: c }: { cache: LanCacheState }) {
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

function useSave(kind: 'uplinks' | 'resolvers', id: string | undefined, onClose: () => void) {
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
            onChange={(v) => set({ device: v ?? '' })} />
          <TextInput label={t('services.port')} placeholder="Te1/0/48" value={form.port} onChange={(e) => set({ port: e.currentTarget.value })} />
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
