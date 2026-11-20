import {
  ActionIcon, Alert, Badge, Button, Checkbox, Group, Modal, Paper, Radio, Select, Stack, Table, Text, TextInput, Title,
} from '@mantine/core'
import { IconCopy, IconPencil, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { get, patch, post } from '@/api/client'
import { useLiveEvent } from '@/api/live'
import {
  COPY_PARTS, pickEvent, TENANT_EVENTS_URL,
  type CopyChanges, type CopyPart, type TenantEvent, type TenantEvents as Data,
} from '@/api/tenantEvents'
import { ConfirmButton } from '@/components/ConfirmButton'
import { StateBadge } from '@/components/State'

const KEY = ['tenant-events'] as const
const NEW = '__new__'

function label(e: TenantEvent | undefined, t: (k: string) => string): string {
  return e ? e.name || t('tenantEvents.unnamed') : ''
}

function StatusBadge({ status }: { status: TenantEvent['status'] }) {
  const { t } = useTranslation()
  return <StateBadge state={status} label={t(`tenantEvents.status.${status}`)} />
}

function NameModal({ title, initial, onClose, onSave, pending, error, children, saveLabel }: {
  title: string; saveLabel?: string; initial: string; onClose: () => void; onSave: (name: string) => void
  pending: boolean; error: Error | null; children?: ReactNode
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(initial)
  return (
    <Modal opened onClose={onClose} title={title} centered>
      <Stack gap="sm">
        <TextInput label={t('tenantEvents.name')} value={name} maxLength={120} data-autofocus
          onChange={(e) => setName(e.currentTarget.value)} />
        {children}
        {error && <Alert color="down" role="alert">{error.message}</Alert>}
        <Button loading={pending} disabled={!name.trim()} onClick={() => onSave(name.trim())}>{saveLabel ?? t('tenantEvents.save')}</Button>
      </Stack>
    </Modal>
  )
}

function NewEvent({ data, onClose, onDone }: { data: Data; onClose: () => void; onDone: (e: TenantEvent) => void }) {
  const { t } = useTranslation()
  const [from, setFrom] = useState<string>(data.live)
  const create = useMutation({
    mutationFn: (name: string) => post<{ event: TenantEvent }>(TENANT_EVENTS_URL, { name, copy_from: from || null }),
    onSuccess: (r) => onDone(r.event),
  })
  const options = [{ value: '', label: t('tenantEvents.startEmpty') },
    ...data.events.map((e) => ({ value: e.id, label: t('tenantEvents.startCopy', { name: label(e, t) }) }))]
  return (
    <NameModal title={t('tenantEvents.newTitle')} saveLabel={t('tenantEvents.create')} initial="" onClose={onClose} onSave={(n) => create.mutate(n)}
      pending={create.isPending} error={create.error}>
      <Select label={t('tenantEvents.startFrom')} data={options} value={from} allowDeselect={false}
        onChange={(v) => setFrom(v ?? '')} />
    </NameModal>
  )
}

function CopyEvent({ data, onClose, onDone }: { data: Data; onClose: () => void; onDone: (name: string) => void }) {
  const { t } = useTranslation()
  const [from, setFrom] = useState(data.current)
  const [to, setTo] = useState<string>(NEW)
  const [newName, setNewName] = useState('')
  const [parts, setParts] = useState<CopyPart[]>(COPY_PARTS)
  const [mode, setMode] = useState<'merge' | 'replace'>('merge')
  const [preview, setPreview] = useState<CopyChanges | null>(null)
  const byId = Object.fromEntries(data.events.map((e) => [e.id, e]))
  const body = { to, parts, mode }
  const look = useMutation({
    mutationFn: () => post<{ changes: CopyChanges }>(`${TENANT_EVENTS_URL}/${from}/copy`, { ...body, preview: true }),
    onSuccess: (r) => setPreview(r.changes),
  })
  const run = useMutation({
    mutationFn: async () => {
      if (to !== NEW) {
        await post(`${TENANT_EVENTS_URL}/${from}/copy`, body)
        return label(byId[to], t)
      }
      // A new event: made empty, then the chosen parts copied in.
      const made = await post<{ event: TenantEvent }>(TENANT_EVENTS_URL, { name: newName.trim() })
      await post(`${TENANT_EVENTS_URL}/${from}/copy`, { ...body, to: made.event.id, mode: 'replace' })
      return made.event.name
    },
    onSuccess: onDone,
  })
  const reset = () => setPreview(null)
  const targets = [{ value: NEW, label: t('tenantEvents.copyToNew') },
    ...data.events.filter((e) => e.id !== from).map((e) => ({ value: e.id, label: label(e, t) }))]
  const ready = parts.length > 0 && (to === NEW ? newName.trim() !== '' : to !== from)
  return (
    <Modal opened onClose={onClose} title={t('tenantEvents.copyTitle')} centered size="lg">
      <Stack gap="sm">
        <Group grow align="flex-start">
          <Select label={t('tenantEvents.copyFrom')} allowDeselect={false} value={from}
            data={data.events.map((e) => ({ value: e.id, label: label(e, t) }))}
            onChange={(v) => { setFrom(v ?? data.current); if (v === to) setTo(NEW); reset() }} />
          <Select label={t('tenantEvents.copyTo')} allowDeselect={false} value={to} data={targets}
            onChange={(v) => { setTo(v ?? NEW); reset() }} />
        </Group>
        {to === NEW && (
          <TextInput label={t('tenantEvents.name')} value={newName} maxLength={120}
            onChange={(e) => setNewName(e.currentTarget.value)} />
        )}
        <Checkbox.Group label={t('tenantEvents.copyParts')} value={parts}
          onChange={(v) => { setParts(v as CopyPart[]); reset() }}>
          <Stack gap={6} mt={6}>
            {COPY_PARTS.map((p) => <Checkbox key={p} value={p} label={t(`tenantEvents.part.${p}`)} />)}
          </Stack>
        </Checkbox.Group>
        <Text size="xs" c="dimmed">{t('tenantEvents.copyNever')}</Text>
        {to !== NEW && (
          <Radio.Group label={t('tenantEvents.mode')} value={mode} onChange={(v) => { setMode(v as 'merge' | 'replace'); reset() }}>
            <Stack gap={6} mt={6}>
              <Radio value="merge" label={t('tenantEvents.modeMerge')} />
              <Radio value="replace" label={t('tenantEvents.modeReplace')} />
            </Stack>
          </Radio.Group>
        )}
        {preview && (
          <Paper withBorder radius="md" p="sm">
            <Text fw={600} size="sm" mb={4}>{t('tenantEvents.previewTitle', { name: label(byId[to], t) })}</Text>
            <Table>
              <Table.Tbody>
                {COPY_PARTS.filter((p) => preview[p]).map((part) => [part, preview[part]] as const).map(([part, c]) => (
                  <Table.Tr key={part}>
                    <Table.Td><Text size="sm">{t(`tenantEvents.part.${part}`)}</Text></Table.Td>
                    <Table.Td>
                      <Text size="sm" c="dimmed">
                        {c.added + c.changed + c.removed === 0 ? t('tenantEvents.nothing') : [
                          c.added ? t('tenantEvents.added', { count: c.added }) : null,
                          c.changed ? t('tenantEvents.changed', { count: c.changed }) : null,
                          c.removed ? t('tenantEvents.removed', { count: c.removed }) : null,
                        ].filter(Boolean).join(' · ')}
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        )}
        {(look.error || run.error) && <Alert color="down" role="alert">{(look.error ?? run.error)?.message}</Alert>}
        <Group justify="flex-end">
          {to !== NEW && (
            <Button variant="default" disabled={!ready} loading={look.isPending} onClick={() => look.mutate()}>
              {t('tenantEvents.preview')}
            </Button>
          )}
          {/* Into an existing event only after its preview, so nobody overwrites a plan blind. */}
          <Button disabled={!ready || (to !== NEW && !preview)} loading={run.isPending} onClick={() => run.mutate()}>
            {t('tenantEvents.doCopy')}
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

/** The tenant's events: which is live, which this browser works on, new events and copies. */
export function TenantEvents({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: KEY, queryFn: () => get<Data>(TENANT_EVENTS_URL) })
  const refresh = () => void qc.invalidateQueries({ queryKey: KEY })
  useLiveEvent('tenant_events', refresh)
  const [dialog, setDialog] = useState<'new' | 'copy' | TenantEvent | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const change = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => patch(`${TENANT_EVENTS_URL}/${id}`, body),
    onSuccess: () => { setDialog(null); refresh() },
  })
  const d = query.data
  if (!d) return null
  const live = d.events.find((e) => e.id === d.live)
  return (
    <Paper withBorder radius="lg" p="md">
      <Group justify="space-between" mb={4} wrap="wrap">
        <Title order={2} size="h4">{t('tenantEvents.title')}</Title>
        {isAdmin && (
          <Group gap="xs">
            <Button size="compact-sm" variant="default" leftSection={<IconCopy size={14} />} onClick={() => setDialog('copy')}>
              {t('tenantEvents.copy')}
            </Button>
            <Button size="compact-sm" leftSection={<IconPlus size={14} />} onClick={() => setDialog('new')}>
              {t('tenantEvents.newEvent')}
            </Button>
          </Group>
        )}
      </Group>
      <Text size="sm" c="dimmed" mb="sm">{t('tenantEvents.intro')}</Text>
      {notice && <Alert color="up" role="status" mb="sm" withCloseButton onClose={() => setNotice(null)}>{notice}</Alert>}
      {change.error && <Alert color="down" role="alert" mb="sm">{change.error.message}</Alert>}
      <Stack gap="sm">
        {d.events.map((e) => (
          <Group key={e.id} justify="space-between" wrap="wrap" gap="xs">
            <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
              <Text fw={600} style={{ overflowWrap: 'anywhere' }}>{label(e, t)}</Text>
              {isAdmin && (
                <ActionIcon variant="subtle" size="sm" aria-label={t('tenantEvents.rename')} onClick={() => setDialog(e)}>
                  <IconPencil size={14} />
                </ActionIcon>
              )}
              <StatusBadge status={e.status} />
              {e.id === d.current && <Badge size="sm" variant="outline" color="gray" tt="none">{t('tenantEvents.current')}</Badge>}
            </Group>
            <Group gap="xs">
              {e.id !== d.current && (
                <Button size="compact-sm" variant="default" onClick={() => void pickEvent(e.status === 'live' ? null : e.id)}>
                  {t('tenantEvents.open')}
                </Button>
              )}
              {isAdmin && e.status !== 'live' && (
                <>
                  <ConfirmButton size="compact-sm" variant="default" label={t('tenantEvents.makeLive')}
                    question={t('tenantEvents.makeLiveQuestion', { name: label(e, t), live: label(live, t) })}
                    onConfirm={() => change.mutate({ id: e.id, body: { status: 'live' } })} />
                  <Button size="compact-sm" variant="subtle"
                    onClick={() => change.mutate({ id: e.id, body: { status: e.status === 'closed' ? 'planning' : 'closed' } })}>
                    {t(e.status === 'closed' ? 'tenantEvents.reopen' : 'tenantEvents.closeEvent')}
                  </Button>
                </>
              )}
            </Group>
          </Group>
        ))}
      </Stack>
      {dialog === 'new' && (
        <NewEvent data={d} onClose={() => setDialog(null)}
          onDone={(e) => { setDialog(null); setNotice(t('tenantEvents.created', { name: e.name })); refresh() }} />
      )}
      {dialog === 'copy' && (
        <CopyEvent data={d} onClose={() => setDialog(null)}
          onDone={(name) => { setDialog(null); setNotice(t('tenantEvents.copied', { name })); refresh() }} />
      )}
      {dialog && typeof dialog === 'object' && (
        <NameModal title={t('tenantEvents.rename')} initial={dialog.name} onClose={() => setDialog(null)}
          onSave={(name) => change.mutate({ id: dialog.id, body: { name } })} pending={change.isPending} error={change.error} />
      )}
    </Paper>
  )
}
