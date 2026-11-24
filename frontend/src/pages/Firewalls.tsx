import {
  Alert, Anchor, Badge, Button, Group, Modal, Paper, SimpleGrid, Stack, Text, Title, Tooltip,
} from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { del, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { FirewallCard, FirewallList, FirewallRange } from '@/api/types'
import { DataTable } from '@/components/DataTable'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { ConfirmButton } from '@bitsandbricks/ui'
import { FirewallLookup } from './firewalls/Lookup'
import { RangeForm } from './firewalls/RangeForm'
import { rangePage, ROUTE_TONE, useSwitchScope, type SwitchScope } from './firewalls/scope'

const STATUS_TONE = { online: 'up', offline: 'down', unknown: 'gray' } as const

/** The firewalls and the seat ranges the core policy-routes to them (issues #470, #866): health, what
 *  each one serves now, and which parts of a range are off their firewall. A range over several
 *  firewalls is cut into equal parts, one per firewall (Mike, 2026-11-24). */
export default function Firewalls() {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const q = useQuery({ queryKey: qk.firewalls, queryFn: () => get<FirewallList>('/api/firewalls'), refetchInterval: 15_000 })
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()
  const scope = useSwitchScope()
  const qc = useQueryClient()
  const imported = useMutation({
    mutationFn: () => post<{ added: number; errors: string[] }>('/api/firewalls/ranges/import'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.firewalls }),
  })
  const data = q.data
  const moved = data?.ranges.flatMap((r) => r.parts.filter((p) => p.state === 'failover' || p.state === 'down')
    .map((p) => ({ ...p, range: r }))) ?? []
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
            <Button onClick={() => setAdding(true)}>{t('firewalls.add')}</Button>
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
              {moved.map((p) => (
                <Text key={`${p.range.id}-${p.cidr}`} size="sm">
                  {p.state === 'down'
                    ? t('firewalls.rangeDown', { range: label(p.range, p.cidr) })
                    : t('firewalls.rangeFailover', { range: label(p.range, p.cidr), now: p.now, intended: p.firewall })}
                </Text>
              ))}
            </Stack>
          </Alert>
        )}
        {data && data.ranges.length > 0 && <FirewallLookup />}
        {data && data.firewalls.length === 0 && (
          <Paper withBorder radius="lg" p="md"><Text c="dimmed">{t('firewalls.none')}</Text></Paper>
        )}
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
          {data?.firewalls.map((f) => <Card key={f.id} card={f} />)}
        </SimpleGrid>
        {data && data.firewalls.length > 0 && (
          <Paper withBorder radius="lg" p="md">
            <Group justify="space-between" align="baseline" mb="sm" wrap="wrap">
              <Title order={2} size="h4">{t('firewalls.ranges', { count: data.ranges.length })}</Title>
              {data.ranges.length > 0 && (
                <Anchor href="/inventory?type=firewall-range" size="sm">{t('firewalls.inInventory')}</Anchor>
              )}
            </Group>
            {data.ranges.length === 0
              ? <Text c="dimmed">{t(canEdit ? 'firewalls.noRangesEdit' : 'firewalls.noRanges')}</Text>
              : <Ranges ranges={data.ranges} scope={scope} canEdit={canEdit} onEdit={(r) => navigate(rangePage(r.id))} />}
          </Paper>
        )}
      </Stack>
      {adding && data && (
        <AddRange names={data.firewalls.map((f) => f.name)} scope={scope} onClose={() => setAdding(false)} />
      )}
    </Layout>
  )
}

function label(r: FirewallRange, cidr: string) {
  return r.name ? `${r.name} (${cidr})` : cidr
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
      {f.taken_over.length > 0 && <Text size="xs" c="warn" mt={4}>{t('firewalls.takenOver', { list: f.taken_over.join(', ') })}</Text>}
    </Paper>
  )
}

function Ranges({ ranges, scope, canEdit, onEdit }: {
  ranges: FirewallRange[]; scope: SwitchScope; canEdit: boolean; onEdit: (r: FirewallRange) => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: (id: string) => del(`/api/firewalls/ranges/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.firewalls }),
  })
  return (
    // One card per range on a phone, so Edit and Remove stay on screen.
    <DataTable label={t('firewalls.ranges', { count: ranges.length })} rows={ranges} rowKey={(r) => r.id} defaultSort={{ id: 'range' }} urlState={false} pageSize={0} bare cards
      columns={[
        { id: 'range', header: t('firewalls.range'), sort: (r) => r.cidr, cell: (r) => (
          <>
            <Text size="sm" ff="monospace">{r.cidr}</Text>
            {r.name && <Text size="xs" c="dimmed">{r.name}</Text>}
            {!!r.switches?.length && (
              <Text size="xs" c="dimmed">{t('firewalls.forSwitches', { switches: r.switches.map((id) => scope.names.get(id) ?? '?').join(', ') })}</Text>
            )}
            {r.source === 'import' && <Badge size="xs" variant="light" color="gray">{t('firewalls.fromPlugin', { plugin: r.plugin || 'NetBox' })}</Badge>}
          </>
        ) },
        { id: 'parts', header: t('firewalls.parts'), card: 'label', wrap: true, sort: (r) => r.state, cell: (r) => (
          <Stack gap={4}>
            {r.parts.map((p) => (
              <Group key={p.cidr} gap={6} wrap="nowrap">
                {r.parts.length > 1 && <Text size="xs" ff="monospace" c="dimmed">{p.cidr}</Text>}
                <Text size="sm" ff="monospace">{p.now ?? p.firewall}</Text>
                <Badge size="sm" color={ROUTE_TONE[p.state]} variant="light">{t(`firewalls.route.${p.state}`)}</Badge>
              </Group>
            ))}
            {r.fallback.length > 0 && <Text size="xs" c="dimmed">{t('firewalls.fallsBack', { list: r.fallback.join(', ') })}</Text>}
          </Stack>
        ) },
        { id: 'seats', header: t('firewalls.seats'), card: 'label', numeric: true, sort: (r) => r.seats, cell: (r) => r.seats },
        ...(canEdit ? [{ id: 'actions', header: null, cell: (r: FirewallRange) => (
          <Group gap={4} justify="flex-end" wrap="nowrap">
            {r.source === 'import' && <Text size="xs" c="dimmed">{t('firewalls.fromPluginHelp', { plugin: r.plugin || 'NetBox' })}</Text>}
            {/* An imported range still takes its switches here: NetBox doesn't know them. */}
            <Button size="compact-sm" variant="default" onClick={() => onEdit(r)}>
              {r.source === 'import' ? t('firewalls.editSwitches') : t('firewalls.edit')}
            </Button>
            <ConfirmButton size="compact-sm" variant="subtle" danger label={t('firewalls.remove')}
              question={t('firewalls.removeQuestion', { range: r.cidr })} onConfirm={() => remove.mutate(r.id)} />
          </Group>
        ) }] : []),
      ]} />
  )
}

function AddRange({ names, scope, onClose }: { names: string[]; scope: SwitchScope; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <Modal opened onClose={onClose} title={t('firewalls.add')}>
      <RangeForm range={null} names={names} scope={scope} onSaved={onClose} />
    </Modal>
  )
}
