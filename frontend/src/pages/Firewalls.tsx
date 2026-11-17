import {
  Alert, Badge, Button, Group, Modal, MultiSelect, NumberInput, Paper, ScrollArea, SimpleGrid, Stack, Table, Text, TextInput, Title,
  Tooltip,
} from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { FirewallCard, FirewallList, FirewallRange } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

const STATUS_TONE = { online: 'up', offline: 'down', unknown: 'gray' } as const
const ROUTE_TONE = { primary: 'up', failover: 'warn', unknown: 'gray', down: 'down' } as const

/** The firewalls and the seat ranges the core routes to them (issue #470): health, what each one
 *  serves now, and which ranges have failed over to a backup. */
export default function Firewalls() {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const q = useQuery({ queryKey: qk.firewalls, queryFn: () => get<FirewallList>('/api/firewalls'), refetchInterval: 15_000 })
  const [editing, setEditing] = useState<FirewallRange | 'new' | null>(null)
  const [splitting, setSplitting] = useState(false)
  const qc = useQueryClient()
  const imported = useMutation({
    mutationFn: () => post<{ added: number; errors: string[] }>('/api/firewalls/ranges/import'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.firewalls }),
  })
  const data = q.data
  const moved = data?.ranges.filter((r) => r.state === 'failover' || r.state === 'down') ?? []
  return (
    <Layout title={t('firewalls.title')}>
      <PageHead title={t('firewalls.title')} desc={t('firewalls.intro')}
        actions={canEdit && data && data.firewalls.length > 0 && (
          <Group gap="xs">
            {data.can_import && (
              <Tooltip label={t('firewalls.importHelp')} multiline w={280}>
                <Button variant="default" loading={imported.isPending} onClick={() => imported.mutate()}>{t('firewalls.import')}</Button>
              </Tooltip>
            )}
            <Button variant="default" onClick={() => setSplitting(true)}>{t('firewalls.split')}</Button>
            <Button onClick={() => setEditing('new')}>{t('firewalls.add')}</Button>
          </Group>
        )} />
      <Stack gap="md">
        {q.error && <Alert color="down" role="alert">{q.error.message}</Alert>}
        {imported.error && <Alert color="down" role="alert">{imported.error.message}</Alert>}
        {imported.data && (
          <Alert color={imported.data.errors.length ? 'warn' : 'up'} role="status" withCloseButton onClose={() => imported.reset()}>
            <Text size="sm">{t('firewalls.importDone', { count: imported.data.added })}</Text>
            {imported.data.errors.map((e) => <Text key={e} size="xs">{e}</Text>)}
          </Alert>
        )}
        {data?.unread && <Alert color="warn">{t('firewalls.unread')}</Alert>}
        {data && data.monitoring === false && <Alert color="gray">{t('firewalls.noMonitoring')}</Alert>}
        {moved.length > 0 && (
          <Alert color={moved.some((r) => r.state === 'down') ? 'down' : 'warn'} title={t('firewalls.moved', { count: moved.length })}>
            <Stack gap={2}>
              {moved.map((r) => (
                <Text key={r.id} size="sm">
                  {r.state === 'down'
                    ? t('firewalls.rangeDown', { range: label(r) })
                    : t('firewalls.rangeFailover', { range: label(r), now: r.now, intended: r.intended })}
                </Text>
              ))}
            </Stack>
          </Alert>
        )}
        {data && data.firewalls.length === 0 && (
          <Paper withBorder radius="lg" p="md"><Text c="dimmed">{t('firewalls.none')}</Text></Paper>
        )}
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
          {data?.firewalls.map((f) => <Card key={f.id} card={f} />)}
        </SimpleGrid>
        {data && data.firewalls.length > 0 && (
          <Paper withBorder radius="lg" p="md">
            <Title order={2} size="h4" mb="sm">{t('firewalls.ranges', { count: data.ranges.length })}</Title>
            {data.ranges.length === 0
              ? <Text c="dimmed">{t(canEdit ? 'firewalls.noRangesEdit' : 'firewalls.noRanges')}</Text>
              : <Ranges ranges={data.ranges} canEdit={canEdit} onEdit={setEditing} />}
          </Paper>
        )}
      </Stack>
      {editing && data && (
        <RangeModal range={editing === 'new' ? null : editing} names={data.firewalls.map((f) => f.name)} onClose={() => setEditing(null)} />
      )}
      {splitting && data && <SplitModal names={data.firewalls.map((f) => f.name)} onClose={() => setSplitting(false)} />}
    </Layout>
  )
}

function label(r: FirewallRange) {
  return r.name ? `${r.name} (${r.cidr})` : r.cidr
}

function Card({ card: f }: { card: FirewallCard }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md" component="section" aria-label={f.name}>
      <Group justify="space-between" wrap="nowrap" mb={4}>
        <Title order={3} size="h5" ff="monospace">{f.name}</Title>
        <Badge color={STATUS_TONE[f.status]} variant={f.status === 'online' ? 'filled' : 'light'}>{t(`firewalls.status.${f.status}`)}</Badge>
      </Group>
      {f.model && <Text size="xs" c="dimmed">{f.model}</Text>}
      <Text size="sm" mt="xs">
        {f.serving.length ? t('firewalls.serving', { count: f.serving.length, seats: f.seats }) : t('firewalls.idle')}
      </Text>
      {f.serving.length > 0 && <Text size="xs" ff="monospace" c="dimmed">{f.serving.join(', ')}</Text>}
      {f.status === 'offline' && f.planned.length > 0 && (
        <Text size="xs" c="down" mt={4}>{t('firewalls.plannedFor', { list: f.planned.join(', ') })}</Text>
      )}
      {f.backup_for.length > 0 && <Text size="xs" c="dimmed" mt={4}>{t('firewalls.backupFor', { list: f.backup_for.join(', ') })}</Text>}
    </Paper>
  )
}

function Ranges({ ranges, canEdit, onEdit }: { ranges: FirewallRange[]; canEdit: boolean; onEdit: (r: FirewallRange) => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: (id: string) => del(`/api/firewalls/ranges/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.firewalls }),
  })
  return (
    <ScrollArea type="auto">
      <Table verticalSpacing="xs" style={{ minWidth: 560, whiteSpace: 'nowrap' }}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t('firewalls.range')}</Table.Th>
            <Table.Th>{t('firewalls.now')}</Table.Th>
            <Table.Th>{t('firewalls.line')}</Table.Th>
            <Table.Th ta="right">{t('firewalls.seats')}</Table.Th>
            {canEdit && <Table.Th />}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {ranges.map((r) => (
            <Table.Tr key={r.id}>
              <Table.Td>
                <Text size="sm" ff="monospace">{r.cidr}</Text>
                {r.name && <Text size="xs" c="dimmed">{r.name}</Text>}
                {r.source === 'import' && <Badge size="xs" variant="light" color="gray">{t('firewalls.fromPlugin', { plugin: r.plugin || 'NetBox' })}</Badge>}
              </Table.Td>
              <Table.Td>
                <Group gap={6} wrap="nowrap">
                  {r.now && <Text size="sm" ff="monospace">{r.now}</Text>}
                  <Badge size="sm" color={ROUTE_TONE[r.state]} variant="light">{t(`firewalls.route.${r.state}`)}</Badge>
                </Group>
              </Table.Td>
              <Table.Td><Text size="sm">{r.firewalls.join(' → ')}</Text></Table.Td>
              <Table.Td ta="right">{r.seats}</Table.Td>
              {canEdit && (
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    {r.source === 'import'
                      ? <Text size="xs" c="dimmed">{t('firewalls.fromPluginHelp', { plugin: r.plugin || 'NetBox' })}</Text>
                      : <Button size="compact-sm" variant="default" onClick={() => onEdit(r)}>{t('firewalls.edit')}</Button>}
                    <ConfirmButton size="compact-sm" variant="subtle" danger label={t('firewalls.remove')}
                      question={t('firewalls.removeQuestion', { range: r.cidr })} onConfirm={() => remove.mutate(r.id)} />
                  </Group>
                </Table.Td>
              )}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  )
}

function RangeModal({ range, names, onClose }: { range: FirewallRange | null; names: string[]; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState({ cidr: range?.cidr ?? '', name: range?.name ?? '', firewalls: range?.firewalls ?? [] })
  const save = useMutation({
    mutationFn: () => (range ? put(`/api/firewalls/ranges/${range.id}`, form) : post('/api/firewalls/ranges', form)),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.firewalls }); onClose() },
  })
  return (
    <Modal opened onClose={onClose} title={range ? t('firewalls.editTitle') : t('firewalls.add')}>
      <Stack gap="sm">
        <TextInput label={t('firewalls.range')} placeholder="192.0.2.0/27" value={form.cidr}
          onChange={(e) => setForm({ ...form, cidr: e.currentTarget.value })} />
        <TextInput label={t('firewalls.name')} placeholder={t('firewalls.namePlaceholder')} value={form.name}
          onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} />
        <MultiSelect label={t('firewalls.line')} description={t('firewalls.lineHelp')} data={names} value={form.firewalls}
          onChange={(v) => setForm({ ...form, firewalls: v })} searchable />
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button loading={save.isPending} disabled={!form.cidr.trim() || form.firewalls.length === 0}
            onClick={() => save.mutate()}>{t('firewalls.save')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

/** How many ranges a split makes, or null while the network isn't one yet. */
function splitCount(cidr: string, size: number | string) {
  const m = /^[0-9a-f.:]+\/(\d{1,3})$/i.exec(cidr.trim())
  const prefix = m ? Number(m[1]) : NaN
  const want = Number(size)
  if (!Number.isInteger(prefix) || !Number.isInteger(want) || want < prefix || want > (cidr.includes(':') ? 128 : 32)) return null
  return want - prefix > 8 ? Infinity : 2 ** (want - prefix)
}

function SplitModal({ names, onClose }: { names: string[]; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState({ cidr: '', size: 24 as number | string, name: '', firewalls: names })
  const count = splitCount(form.cidr, form.size)
  const save = useMutation({
    mutationFn: () => post('/api/firewalls/ranges/split', { ...form, size: Number(form.size) }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: qk.firewalls }); onClose() },
  })
  return (
    <Modal opened onClose={onClose} title={t('firewalls.split')}>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t('firewalls.splitIntro')}</Text>
        <TextInput label={t('firewalls.splitNetwork')} placeholder="198.51.100.0/22" value={form.cidr}
          onChange={(e) => setForm({ ...form, cidr: e.currentTarget.value })} />
        <NumberInput label={t('firewalls.splitSize')} description={t('firewalls.splitSizeHelp')} min={1} max={128}
          prefix="/" value={form.size} onChange={(v) => setForm({ ...form, size: v })} />
        <TextInput label={t('firewalls.name')} description={t('firewalls.splitNameHelp')} placeholder={t('firewalls.splitNamePlaceholder')}
          value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} />
        <MultiSelect label={t('firewalls.splitLine')} description={t('firewalls.lineHelp')} data={names} value={form.firewalls}
          onChange={(v) => setForm({ ...form, firewalls: v })} searchable />
        {count === Infinity
          ? <Text size="sm" c="down">{t('firewalls.splitTooMany')}</Text>
          : count !== null && <Text size="sm">{t('firewalls.splitCount', { count })}</Text>}
        {save.error && <Alert color="down" role="alert">{save.error.message}</Alert>}
        <Group justify="flex-end">
          <Button loading={save.isPending} disabled={count === null || count === Infinity || form.firewalls.length === 0}
            onClick={() => save.mutate()}>{t('firewalls.splitGo')}</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
