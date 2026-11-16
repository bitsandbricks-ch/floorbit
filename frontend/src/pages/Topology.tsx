import {
  Alert, Badge, Box, Button, Drawer, Group, Modal, Paper, Select, SimpleGrid, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { LinkSuggestion, SwitchLink, Topology as TopologyData, TopologyNode, TopologyUplink } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { NODE_H, NODE_W, gbit, layout, placeUplinks } from './topology/layout'

const COLOR: Record<string, string> = {
  cat5e: 'var(--mantine-color-blue-6)', cat6: 'var(--mantine-color-blue-6)', cat6a: 'var(--mantine-color-blue-6)',
  'fiber-sm': 'var(--mantine-color-yellow-6)', 'fiber-mm': 'var(--mantine-color-cyan-6)', dac: 'var(--mantine-color-violet-6)',
  '': 'var(--mantine-color-gray-5)',
}
const WIDTH: Record<number, number> = { 1: 1.5, 10: 2.5, 25: 3, 40: 4, 100: 5 }


type Picked = { kind: 'link'; id: string } | { kind: 'node'; name: string } | { kind: 'uplink'; id: string } | null

const UPLINK_COLOR = { up: 'var(--mantine-color-green-6)', warn: 'var(--mantine-color-orange-6)', down: 'var(--mantine-color-red-6)', unknown: 'var(--mantine-color-gray-5)' } as const
type Draft = Partial<SwitchLink> & { id?: string }

/** The network's links between switches (issue #468): type and speed, down or slower than planned,
 *  and what LLDP sees that no link explains yet. */
export default function Topology() {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const phone = useMediaQuery('(max-width: 48em)')
  const q = useQuery({ queryKey: qk.topology, queryFn: () => get<TopologyData>('/api/links'), refetchInterval: 30_000 })
  const [picked, setPicked] = useState<Picked>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const data = q.data
  const placed = useMemo(() => (data ? layout(data.nodes, data.links) : null), [data])
  const lines = useMemo(() => (placed && data ? placeUplinks(placed, data.uplinks ?? []) : null), [placed, data])
  const uplink = picked?.kind === 'uplink' ? data?.uplinks.find((u) => u.id === picked.id) : undefined
  const link = picked?.kind === 'link' ? data?.links.find((l) => l.id === picked.id) : undefined
  const node = picked?.kind === 'node' ? data?.nodes.find((n) => n.name === picked.name) : undefined
  const problems = data?.links.filter((l) => l.issue) ?? []

  const panel = uplink ? <UplinkPanel uplink={uplink} />
    : link ? <LinkPanel link={link} canEdit={canEdit} onEdit={() => setDraft(link)} onGone={() => setPicked(null)} />
    : node ? <NodePanel name={node.name} role={node.role} status={node.status} links={data!.links.filter((l) => l.a === node.name || l.b === node.name)}
      onPick={(id) => setPicked({ kind: 'link', id })} />
      : <Text c="dimmed" size="sm">{t('topology.pickHint')}</Text>

  return (
    <Layout title={t('topology.title')}>
      <PageHead title={t('topology.title')} desc={t('topology.intro')}
        actions={canEdit && <Button onClick={() => setDraft({})}>{t('topology.add')}</Button>} />
      <Stack gap="md">
        {q.error && <Alert color="down" role="alert">{q.error.message}</Alert>}
        {problems.length > 0 && (
          <Alert color={problems.some((l) => l.issue === 'down') ? 'down' : 'warn'} title={t('topology.problems', { count: problems.length })}>
            <Stack gap={2}>
              {problems.map((l) => (
                <Text key={l.id} size="sm" component="button" onClick={() => setPicked({ kind: 'link', id: l.id })}
                  style={{ all: 'unset', cursor: 'pointer', textDecoration: 'underline dotted' }}>
                  {t(`topology.issue.${l.issue}`, { a: `${l.a} ${l.a_port}`, b: `${l.b} ${l.b_port}`, planned: `${l.speed}G`, actual: gbit(l.speed_bps) })}
                </Text>
              ))}
            </Stack>
          </Alert>
        )}
        {data && data.links.length === 0 && (
          <Paper withBorder radius="lg" p="md"><Text c="dimmed">{t(canEdit ? 'topology.emptyEdit' : 'topology.empty')}</Text></Paper>
        )}
        {data && placed && lines && data.links.length > 0 && (
          <Box style={{ display: 'grid', gap: 16, gridTemplateColumns: phone ? '1fr' : 'minmax(0, 1fr) 300px' }}>
            <Paper withBorder radius="lg" p="sm" style={{ overflowX: 'auto' }}>
              <svg role="img" aria-label={t('topology.diagram', { count: data.links.length })}
                viewBox={`-10 -10 ${lines.width + 20} ${lines.height + 20}`}
                style={{ display: 'block', width: '100%', minWidth: phone ? Math.min(lines.width, 720) : undefined, height: 'auto' }}>
                {lines.boxes.map(({ uplink: u, x, y, to }) => {
                  const chosen = picked?.kind === 'uplink' && picked.id === u.id
                  return (
                    <g key={u.id} className="fb-uplink" data-status={u.status} onClick={() => setPicked({ kind: 'uplink', id: u.id })} style={{ cursor: 'pointer' }}>
                      <title>{`${u.name}: ${u.device} ${u.port} · ${t(`topology.uplinkStatus.${u.status}`)}`}</title>
                      <line x1={x + NODE_W / 2} y1={y + NODE_H} x2={to.x + lines.dx + NODE_W / 2} y2={to.y + lines.dy}
                        stroke={UPLINK_COLOR[u.status]} strokeWidth={3} strokeDasharray={u.status === 'down' ? '6 4' : undefined} strokeLinecap="round" />
                      {/* A cloud-ish pill, so the internet doesn't read as one more switch. */}
                      <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={NODE_H / 2} fill="var(--mantine-color-body)"
                        stroke={chosen ? 'var(--mantine-primary-color-filled)' : UPLINK_COLOR[u.status]} strokeWidth={chosen ? 2.5 : 1.8} />
                      <text x={x + NODE_W / 2} y={y + NODE_H / 2} dominantBaseline="central" textAnchor="middle" fontSize={12}
                        fill="var(--mantine-color-text)" fontWeight={600}>
                        {u.name.length > 15 ? `${u.name.slice(0, 14)}…` : u.name}
                      </text>
                    </g>
                  )
                })}
                <g transform={`translate(${lines.dx} ${lines.dy})`}>
                {data.links.map((l) => {
                  const a = placed.placed.get(l.a.toLowerCase()), b = placed.placed.get(l.b.toLowerCase())
                  if (!a || !b) return null
                  const [top, bottom] = a.y <= b.y ? [a, b] : [b, a]
                  const same = top.y === bottom.y
                  const x1 = top.x + NODE_W / 2, y1 = same ? top.y + NODE_H / 2 : top.y + NODE_H
                  const x2 = bottom.x + NODE_W / 2, y2 = same ? bottom.y + NODE_H / 2 : bottom.y
                  const color = l.issue === 'down' ? 'var(--mantine-color-red-6)' : l.issue === 'slow' ? 'var(--mantine-color-orange-6)' : COLOR[l.type]
                  const chosen = picked?.kind === 'link' && picked.id === l.id
                  return (
                    <g key={l.id} onClick={() => setPicked({ kind: 'link', id: l.id })} style={{ cursor: 'pointer' }}>
                      <title>{`${l.a} ${l.a_port} – ${l.b} ${l.b_port}${l.speed ? ` · ${l.speed}G` : ''}`}</title>
                      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth={14} />
                      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={(WIDTH[l.speed ?? 0] ?? 1.5) + (chosen ? 2 : 0)}
                        strokeDasharray={l.issue === 'down' ? '6 4' : l.type === '' ? '2 3' : undefined} strokeLinecap="round" />
                    </g>
                  )
                })}
                {[...placed.placed.values()].map((p) => {
                  const chosen = picked?.kind === 'node' && picked.name === p.node.name
                  return (
                    <g key={p.node.id} transform={`translate(${p.x} ${p.y})`} onClick={() => setPicked({ kind: 'node', name: p.node.name })}
                      style={{ cursor: 'pointer' }}>
                      <title>{`${p.node.name}: ${t(`topology.status.${p.node.status}`)}`}</title>
                      {/* A box that is down: red, dashed and struck through, so it doesn't rely on colour. */}
                      <rect width={NODE_W} height={NODE_H} rx={8} fill={p.node.status === 'offline' ? 'var(--mantine-color-red-light)' : 'var(--mantine-color-body)'}
                        stroke={chosen ? 'var(--mantine-primary-color-filled)' : p.node.status === 'offline' ? 'var(--mantine-color-red-6)' : 'var(--mantine-color-default-border)'}
                        strokeWidth={chosen || p.node.status === 'offline' ? 2.5 : 1.2} strokeDasharray={p.node.status === 'offline' ? '6 4' : undefined}
                        data-status={p.node.status} />
                      <circle cx={10} cy={10} r={4} fill={p.node.status === 'online' ? 'var(--mantine-color-green-6)' : p.node.status === 'offline' ? 'var(--mantine-color-red-6)' : 'var(--mantine-color-gray-5)'} />
                      <text x={NODE_W / 2} y={NODE_H / 2} dominantBaseline="central" textAnchor="middle" fontSize={13}
                        fill="var(--mantine-color-text)" fontWeight={p.node.role === 'switch' ? 400 : 600}>
                        {p.node.name.length > 15 ? `${p.node.name.slice(0, 14)}…` : p.node.name}
                      </text>
                    </g>
                  )
                })}
                </g>
              </svg>
              <Legend />
            </Paper>
            {phone
              ? <Drawer opened={!!picked} onClose={() => setPicked(null)} position="bottom" size="55%"
                aria-label={link ? t('topology.link') : node?.name}>{panel}</Drawer>
              : <Paper withBorder radius="lg" p="md" style={{ alignSelf: 'start' }}>{panel}</Paper>}
          </Box>
        )}
        {placed && placed.loose.length > 0 && data!.links.length > 0 && (
          <Text size="sm" c="dimmed">{t('topology.loose', { names: placed.loose.map((n) => n.name).join(', ') })}</Text>
        )}
        {data && data.suggestions.length > 0 && (
          <Paper withBorder radius="lg" p="md">
            <Title order={3} size="h5" mb={4}>{t('topology.suggestions', { count: data.suggestions.length })}</Title>
            <Text size="sm" c="dimmed" mb="sm">{t('topology.suggestionsHint')}</Text>
            <Stack gap={6}>
              {data.suggestions.map((s) => (
                <Group key={`${s.a}${s.a_port}${s.b}${s.b_port}`} justify="space-between" wrap="nowrap" gap="xs">
                  <Text size="sm" ff="monospace" style={{ overflowWrap: 'anywhere' }}>
                    {s.a} {s.a_port} – {s.b} {s.b_port}{s.protocol ? ` (${s.protocol.toUpperCase()})` : ''}
                  </Text>
                  {canEdit && <Button size="compact-sm" variant="default" onClick={() => setDraft(fromSuggestion(s))}>{t('topology.addThis')}</Button>}
                </Group>
              ))}
            </Stack>
          </Paper>
        )}
      </Stack>
      {draft && data && <LinkModal draft={draft} data={data} onClose={() => setDraft(null)} />}
    </Layout>
  )
}

function fromSuggestion(s: LinkSuggestion): Draft {
  return { a: s.a, a_port: s.a_port, b: s.b, b_port: s.b_port, speed: s.speed, type: '' }
}

function Legend() {
  const { t } = useTranslation()
  const items: [string, string, string?][] = [
    [t('topology.media.copper'), COLOR.cat6], [t('topology.types.fiber-sm'), COLOR['fiber-sm']],
    [t('topology.types.fiber-mm'), COLOR['fiber-mm']], [t('topology.types.dac'), COLOR.dac],
    [t('topology.slow'), 'var(--mantine-color-orange-6)'], [t('topology.down'), 'var(--mantine-color-red-6)', '6 4'],
  ]
  return (
    <Group gap="md" mt="xs" px={4}>
      {items.map(([label, color, dash]) => (
        <Group key={label} gap={6} wrap="nowrap">
          <svg width={24} height={8} aria-hidden="true"><line x1={1} y1={4} x2={23} y2={4} stroke={color} strokeWidth={3} strokeDasharray={dash} /></svg>
          <Text size="xs" c="dimmed">{label}</Text>
        </Group>
      ))}
      <Text size="xs" c="dimmed">{t('topology.thicker')}</Text>
    </Group>
  )
}

function LinkPanel({ link: l, canEdit, onEdit, onGone }: { link: SwitchLink; canEdit: boolean; onEdit: () => void; onGone: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: () => del(`/api/links/${l.id}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.topology }); onGone() },
  })
  const tone = l.issue === 'down' ? 'down' : l.issue === 'slow' ? 'warn' : l.state === 'up' ? 'up' : 'gray'
  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Title order={3} size="h5">{t('topology.link')}</Title>
        <Badge color={tone} variant="light">{l.issue ? t(`topology.${l.issue}`) : t(`topology.state.${l.state}`)}</Badge>
      </Group>
      <Text size="sm" ff="monospace">{l.a} {l.a_port}</Text>
      <Text size="sm" ff="monospace">{l.b} {l.b_port}</Text>
      <SimpleGrid cols={2} spacing={4}>
        <Text size="sm" c="dimmed">{t('topology.type')}</Text><Text size="sm">{l.type ? t(`topology.types.${l.type}`) : '–'}</Text>
        <Text size="sm" c="dimmed">{t('topology.planned')}</Text><Text size="sm">{l.speed ? `${l.speed}G` : '–'}</Text>
        <Text size="sm" c="dimmed">{t('topology.actual')}</Text><Text size="sm">{gbit(l.speed_bps) || '–'}</Text>
      </SimpleGrid>
      {l.note && <Text size="sm">{l.note}</Text>}
      {canEdit && (
        <Group gap="xs" mt={4}>
          <Button size="compact-sm" variant="default" onClick={onEdit}>{t('topology.edit')}</Button>
          <ConfirmButton size="compact-sm" variant="subtle" danger label={t('topology.remove')}
            question={t('topology.removeQuestion', { a: l.a, b: l.b })} onConfirm={() => remove.mutate()} />
        </Group>
      )}
    </Stack>
  )
}

function NodePanel({ name, role, status, links, onPick }: {
  name: string; role: string; status: TopologyNode['status']; links: SwitchLink[]; onPick: (id: string) => void
}) {
  const { t } = useTranslation()
  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Title order={3} size="h5">{name}</Title>
        <Badge color={status === 'online' ? 'up' : status === 'offline' ? 'down' : 'gray'} variant="light">{t(`topology.status.${status}`)}</Badge>
      </Group>
      <Text size="sm" c="dimmed">{t(`topology.roles.${role}`, { defaultValue: role })} · {t('topology.links', { count: links.length })}</Text>
      {links.map((l) => {
        const [mine, other, otherPort] = l.a === name ? [l.a_port, l.b, l.b_port] : [l.b_port, l.a, l.a_port]
        return (
          <Button key={l.id} variant="subtle" size="compact-sm" justify="space-between" onClick={() => onPick(l.id)}
            color={l.issue === 'down' ? 'down' : l.issue === 'slow' ? 'warn' : undefined}
            rightSection={l.speed ? `${l.speed}G` : undefined} styles={{ label: { whiteSpace: 'normal', textAlign: 'left' } }}>
            {mine} → {other} {otherPort}
          </Button>
        )
      })}
    </Stack>
  )
}

function LinkModal({ draft, data, onClose }: { draft: Draft; data: TopologyData; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    a: draft.a ?? '', a_port: draft.a_port ?? '', b: draft.b ?? '', b_port: draft.b_port ?? '',
    type: draft.type ?? '', speed: draft.speed ? String(draft.speed) : '', note: draft.note ?? '',
  })
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })
  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, speed: form.speed ? Number(form.speed) : null }
      return draft.id ? put(`/api/links/${draft.id}`, body) : post('/api/links', body)
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.topology }); onClose() },
  })
  const switches = data.nodes.map((n) => n.name)
  return (
    <Modal opened onClose={onClose} title={draft.id ? t('topology.editTitle') : t('topology.add')} size="lg">
      <Stack gap="sm">
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <Select label={t('topology.from')} data={switches} searchable value={form.a || null} onChange={(v) => set({ a: v ?? '' })} />
          <TextInput label={t('topology.fromPort')} placeholder="Te1/1/1" value={form.a_port} onChange={(e) => set({ a_port: e.currentTarget.value })} />
          <Select label={t('topology.to')} data={switches} searchable value={form.b || null} onChange={(v) => set({ b: v ?? '' })} />
          <TextInput label={t('topology.toPort')} placeholder="Te1/0/1" value={form.b_port} onChange={(e) => set({ b_port: e.currentTarget.value })} />
          <Select label={t('topology.type')} clearable value={form.type || null} onChange={(v) => set({ type: v ?? '' })}
            data={data.types.map((v) => ({ value: v, label: t(`topology.types.${v}`) }))} />
          <Select label={t('topology.speed')} clearable value={form.speed || null} onChange={(v) => set({ speed: v ?? '' })}
            data={data.speeds.map((v) => ({ value: String(v), label: `${v}G` }))} />
        </SimpleGrid>
        <TextInput label={t('topology.note')} value={form.note} onChange={(e) => set({ note: e.currentTarget.value })} />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button loading={save.isPending} disabled={!form.a || !form.b || !form.a_port.trim() || !form.b_port.trim()}
            onClick={() => save.mutate()}>{t('topology.save')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function UplinkPanel({ uplink: u }: { uplink: TopologyUplink }) {
  const { t } = useTranslation()
  const tone = { up: 'up', warn: 'warn', down: 'down', unknown: 'gray' }[u.status]
  return (
    <Stack gap="xs">
      <Group justify="space-between" wrap="nowrap">
        <Title order={3} size="h5">{u.name}</Title>
        <Badge color={tone} variant="light">{t(`topology.uplinkStatus.${u.status}`)}</Badge>
      </Group>
      <Text size="sm" c="dimmed">{t('topology.uplink')}</Text>
      <SimpleGrid cols={2} spacing={4}>
        <Text size="sm" c="dimmed">{t('topology.uplinkPort')}</Text><Text size="sm" ff="monospace">{u.device} {u.port}</Text>
        <Text size="sm" c="dimmed">{t('topology.uplinkCapacity')}</Text><Text size="sm">{u.capacity_mbps ? `${u.capacity_mbps} Mbit/s` : '–'}</Text>
        <Text size="sm" c="dimmed">{t('topology.uplinkUsed')}</Text><Text size="sm">{u.utilization != null ? `${Math.round(u.utilization * 100)} %` : '–'}</Text>
      </SimpleGrid>
      <Button size="compact-sm" variant="default" component="a" href="/services" mt={4} style={{ alignSelf: 'flex-start' }}>{t('topology.openServices')}</Button>
    </Stack>
  )
}
