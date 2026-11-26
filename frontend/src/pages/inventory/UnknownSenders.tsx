import { Badge, Button, Chip, Group, Select, Stack, Switch, Text, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useUnknownSenders, type UnknownSender } from '@/api/unknownSenders'
import { EmptyState, PanelSection, SidePanel } from '@bitsandbricks/ui'
import { ago, dateTime } from '@/lib/time'

/** Devices that send syslog, traps, streams or flows but aren't in the inventory (issue #1443): a
 *  chip on the inventory's filter row and, at ?view=unknown, a side panel to add or ignore them. */
export function UnknownSenders({ canEdit, roles }: { canEdit: boolean; roles: string[] }) {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const open = params.get('view') === 'unknown'
  const [showIgnored, setShowIgnored] = useState(false)
  const { data } = useUnknownSenders()
  const all = data?.senders ?? []
  const waiting = all.filter((s) => !s.ignored)
  const shown = showIgnored ? all : waiting
  const setOpen = (on: boolean) => setParams((p) => {
    const next = new URLSearchParams(p)
    if (on) next.set('view', 'unknown')
    else next.delete('view')
    return next
  }, { replace: true })
  if (!waiting.length && !open) return null
  return (
    <>
      <Chip size="sm" color="warn" variant="outline" checked={open} onChange={setOpen}>
        {t('inventory.unknown.chip', { count: waiting.length })}
      </Chip>
      <SidePanel opened={open} onClose={() => setOpen(false)} title={t('inventory.unknown.title')}
        subtitle={t('inventory.unknown.desc')} padded={false} resizable={{ storageKey: 'floorbit.unknownSenders.width' }}>
        <PanelSection right={all.length > waiting.length && (
          <Switch size="xs" checked={showIgnored} onChange={(e) => setShowIgnored(e.currentTarget.checked)}
            label={t('inventory.unknown.showIgnored', { count: all.length - waiting.length })} />
        )}>
          {!shown.length
            ? <EmptyState title={t('inventory.unknown.none')} description={t('inventory.unknown.noneDesc')} />
            : <Stack gap="md">{shown.map((s) => <SenderRow key={s.address} s={s} canEdit={canEdit} roles={roles} />)}</Stack>}
        </PanelSection>
      </SidePanel>
    </>
  )
}

function SenderRow({ s, canEdit, roles }: { s: UnknownSender; canEdit: boolean; roles: string[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState(s.name || s.address)
  const [role, setRole] = useState(roles.includes('switch') ? 'switch' : roles[0] ?? 'other')
  const done = () => void qc.invalidateQueries({ queryKey: qk.inventoryAll })
  const ignore = useMutation({ mutationFn: (on: boolean) => post('/api/inventory/unknown-senders/ignore', { address: s.address, ignored: on }), onSuccess: done })
  const add = useMutation({ mutationFn: () => post('/api/inventory', { name: name.trim(), role, mgmt_ip: s.address }), onSuccess: done })
  const error = (add.error ?? ignore.error) as Error | null
  return (
    <Stack gap={4} role="group" aria-label={s.address} style={s.ignored ? { opacity: 0.6 } : undefined}>
      <Group gap="xs" wrap="wrap">
        <Text ff="monospace" fw={600}>{s.address}</Text>
        {s.name && <Text size="sm" c="dimmed">{s.name}</Text>}
        {s.ignored && <Badge size="xs" variant="outline" color="gray" tt="none">{t('inventory.unknown.ignored')}</Badge>}
      </Group>
      <Group gap={4}>
        {Object.entries(s.kinds).map(([kind, n]) => (
          <Badge key={kind} size="sm" variant="light" color="gray" tt="none">{t(`inventory.unknown.kind.${kind}`, { count: n })}</Badge>
        ))}
      </Group>
      <Text size="xs" c="dimmed">
        <span title={dateTime(s.last)}>{t('inventory.unknown.heard', { last: ago(s.last), first: ago(s.first) })}</span>
        {s.agents.length > 0 && ` · ${t('inventory.unknown.via', { agents: s.agents.join(', ') })}`}
      </Text>
      {canEdit && !adding && (
        <Group gap="xs" mt={2}>
          <Button size="xs" variant="light" onClick={() => setAdding(true)}>{t('inventory.unknown.add')}</Button>
          <Button size="xs" variant="subtle" color="gray" loading={ignore.isPending} onClick={() => ignore.mutate(!s.ignored)}>
            {s.ignored ? t('inventory.unknown.unignore') : t('inventory.unknown.ignore')}
          </Button>
        </Group>
      )}
      {canEdit && adding && (
        <Group gap="xs" align="flex-end" wrap="wrap" mt={2}>
          <TextInput size="xs" label={t('inventory.field.name')} value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <Select size="xs" label={t('inventory.field.role')} value={role} onChange={(v) => v && setRole(v)} allowDeselect={false}
            data={roles.map((r) => ({ value: r, label: t(`inventory.role.${r}`, { defaultValue: r }) }))} w={150} />
          <Button size="xs" loading={add.isPending} disabled={!name.trim()} onClick={() => add.mutate()}>{t('inventory.unknown.addNow')}</Button>
          <Button size="xs" variant="subtle" color="gray" onClick={() => setAdding(false)}>{t('common.cancel')}</Button>
        </Group>
      )}
      {error && <Text size="xs" className="fb-tone-err" role="alert">{error.message}</Text>}
    </Stack>
  )
}
