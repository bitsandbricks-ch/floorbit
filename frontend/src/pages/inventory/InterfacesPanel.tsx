import { ActionIcon, Badge, Button, Group, Modal, Select, Stack, Switch, Table, Text, TextInput, Tooltip } from '@mantine/core'
import { IconLock, IconLockOpen, IconPencil, IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post } from '@/api/client'
import type { DeviceDetail, DeviceInterface, InterfaceField } from '@/api/types'
import { speedLabel } from './model'

const SPEEDS = [10, 100, 1000, 2500, 5000, 10000, 25000, 40000, 50000, 100000, 400000]
const TYPES = ['copper', 'fiber', 'dac', 'virtual', 'lag', 'wireless', 'mgmt', 'other']
const MODES = ['access', 'trunk', 'routed']


type Draft = { type: string; speed_mbps: string; mac: string; ips: string; vlan: string; mode: string; description: string; enabled: boolean; mgmt: boolean; lag: string }

function draftOf(i: DeviceInterface): Draft {
  return {
    type: i.type, speed_mbps: i.speed_mbps ? String(i.speed_mbps) : '', mac: i.mac, ips: i.ips.join(', '), vlan: i.vlan ? String(i.vlan) : '',
    mode: i.mode, description: i.description, enabled: i.enabled, mgmt: i.mgmt, lag: i.lag,
  }
}

function changesOf(before: Draft, after: Draft) {
  const out: Record<string, unknown> = {}
  for (const k of Object.keys(after) as (keyof Draft)[]) {
    if (after[k] === before[k]) continue
    if (k === 'speed_mbps' || k === 'vlan') out[k] = after[k] ? Number(after[k]) : null
    else out[k] = after[k]
  }
  return out
}

function EditInterface({ device, iface, onClose, onSaved, sourceName }: {
  device: DeviceDetail; iface: DeviceInterface; onClose: () => void; onSaved: () => void; sourceName: (id: string) => string
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Draft>(() => draftOf(iface))
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof Draft>(k: K) => (v: Draft[K]) => setDraft((d) => ({ ...d, [k]: v }))
  const url = `/api/inventory/${encodeURIComponent(device.id)}/interfaces/${encodeURIComponent(iface.id)}`
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch<DeviceInterface>(url, body),
    onSuccess: (_r, body) => { onSaved(); if (!('unlock' in body)) onClose() },
    onError: (e) => setError(e.message),
  })
  const lock = (f: InterfaceField) => iface.locked.includes(f) && (
    <Tooltip label={t('inventory.unlock', { source: sourceName(iface.sources[0] ?? '') })}>
      <ActionIcon variant="subtle" color="warn" aria-label={t('inventory.unlock', { source: sourceName(iface.sources[0] ?? '') })}
        onClick={() => save.mutate({ unlock: [f] })}>
        <IconLockOpen size={16} />
      </ActionIcon>
    </Tooltip>
  )
  const lags = device.interfaces.filter((i) => i.type === 'lag' && i.id !== iface.id).map((i) => i.name)
  const changes = changesOf(draftOf(iface), draft)
  return (
    <Modal opened onClose={onClose} title={t('inventory.ifaces.edit', { name: iface.name, device: device.name })} size="lg">
      <form onSubmit={(e) => { e.preventDefault(); save.mutate(changes) }}>
        <Stack gap="sm">
          <Group grow align="flex-start">
            <Select label={t('inventory.ifaces.type')} data={TYPES.map((v) => ({ value: v, label: t(`inventory.ifaces.types.${v}`) }))}
              value={draft.type || null} onChange={(v) => set('type')(v ?? '')} clearable rightSection={lock('type')} />
            <Select label={t('inventory.ifaces.speed')} data={SPEEDS.map((v) => ({ value: String(v), label: speedLabel(v) }))}
              value={draft.speed_mbps || null} onChange={(v) => set('speed_mbps')(v ?? '')} clearable rightSection={lock('speed_mbps')} />
          </Group>
          <Group grow align="flex-start">
            <Select label={t('inventory.ifaces.mode')} data={MODES.map((v) => ({ value: v, label: t(`inventory.ifaces.modes.${v}`) }))}
              value={draft.mode || null} onChange={(v) => set('mode')(v ?? '')} clearable rightSection={lock('mode')} />
            <TextInput label={t('inventory.ifaces.vlan')} value={draft.vlan} inputMode="numeric" placeholder="10"
              onChange={(e) => set('vlan')(e.currentTarget.value.replace(/\D/g, ''))} rightSection={lock('vlan')} />
          </Group>
          <TextInput label={t('inventory.ifaces.ips')} value={draft.ips} placeholder="192.0.2.1/24, 2001:db8::1/64"
            styles={{ input: { fontFamily: 'var(--font-mono)' } }} onChange={(e) => set('ips')(e.currentTarget.value)} rightSection={lock('ips')} />
          <Group grow align="flex-start">
            <TextInput label={t('inventory.ifaces.mac')} value={draft.mac} placeholder="00:00:5e:00:53:01"
              styles={{ input: { fontFamily: 'var(--font-mono)' } }} onChange={(e) => set('mac')(e.currentTarget.value)} rightSection={lock('mac')} />
            <Select label={t('inventory.ifaces.lag')} data={lags} value={draft.lag || null} onChange={(v) => set('lag')(v ?? '')} clearable
              placeholder={lags.length ? undefined : t('inventory.ifaces.noLag')} disabled={!lags.length && !draft.lag} />
          </Group>
          <TextInput label={t('inventory.ifaces.description')} value={draft.description} maxLength={200}
            onChange={(e) => set('description')(e.currentTarget.value)} rightSection={lock('description')} />
          <Group>
            <Switch label={t('inventory.ifaces.enabled')} checked={draft.enabled} onChange={(e) => set('enabled')(e.currentTarget.checked)} />
            <Switch label={t('inventory.ifaces.mgmt')} checked={draft.mgmt} onChange={(e) => set('mgmt')(e.currentTarget.checked)} />
          </Group>
          {iface.locked.length > 0 && (
            <Text size="xs" c="dimmed"><IconLock size={12} /> {t('inventory.ifaces.lockedHint', { source: sourceName(iface.sources[0] ?? '') })}</Text>
          )}
          {error && <Text className="fb-tone-err" role="alert">✕ {error}</Text>}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
            <Button type="submit" loading={save.isPending} disabled={!Object.keys(changes).length}>{t('inventory.save')}</Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

export function InterfacesPanel({ device, canEdit, sourceName, onChanged }: {
  device: DeviceDetail; canEdit: boolean; sourceName: (id: string) => string; onChanged: () => void
}) {
  const { t } = useTranslation()
  const [names, setNames] = useState('')
  const [type, setType] = useState<string | null>(null)
  const [speed, setSpeed] = useState<string | null>(null)
  const [editing, setEditing] = useState<DeviceInterface | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const base = `/api/inventory/${encodeURIComponent(device.id)}/interfaces`
  const add = useMutation({
    mutationFn: () => post<{ added: DeviceInterface[] }>(base, { names, ...(type ? { type } : {}), ...(speed ? { speed_mbps: Number(speed) } : {}) }),
    onSuccess: ({ added }) => { setNames(''); onChanged(); setMessage({ ok: true, text: t('inventory.ifaces.added', { count: added.length }) }) },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const remove = useMutation({
    mutationFn: (i: DeviceInterface) => del<{ result: string }>(`${base}/${encodeURIComponent(i.id)}`),
    onSuccess: () => onChanged(),
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const show = useMutation({
    mutationFn: (i: DeviceInterface) => patch(`${base}/${encodeURIComponent(i.id)}`, { hidden: false }),
    onSuccess: () => onChanged(),
  })
  const fromMonitoring = useMutation({
    mutationFn: () => post<{ added: number; updated: number; gone: number }>('/api/inventory/interfaces/sync', { devices: [device.name] }),
    onSuccess: (r) => { onChanged(); setMessage({ ok: true, text: t('inventory.ifaces.synced', { added: r.added, updated: r.updated, gone: r.gone }) }) },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  return (
    <Stack gap="sm">
      {canEdit && (
        <form onSubmit={(e) => { e.preventDefault(); if (names.trim()) add.mutate() }}>
          <Group gap="xs" align="flex-end" wrap="wrap">
            <TextInput label={t('inventory.ifaces.names')} placeholder="Gi1/0/1-48" value={names} onChange={(e) => setNames(e.currentTarget.value)}
              styles={{ input: { fontFamily: 'var(--font-mono)' } }} style={{ flex: '1 1 160px' }} description={t('inventory.ifaces.namesHint')} />
            <Select label={t('inventory.ifaces.type')} w={120} data={TYPES.map((v) => ({ value: v, label: t(`inventory.ifaces.types.${v}`) }))}
              value={type} onChange={setType} clearable />
            <Select label={t('inventory.ifaces.speed')} w={100} data={SPEEDS.map((v) => ({ value: String(v), label: speedLabel(v) }))}
              value={speed} onChange={setSpeed} clearable />
            <Button type="submit" leftSection={<IconPlus size={14} />} loading={add.isPending} disabled={!names.trim()}>{t('inventory.ifaces.add')}</Button>
          </Group>
        </form>
      )}
      {canEdit && (
        <Group justify="flex-end">
          <Button size="xs" variant="subtle" loading={fromMonitoring.isPending} onClick={() => fromMonitoring.mutate()}>
            {t('inventory.ifaces.fromMonitoring')}
          </Button>
        </Group>
      )}
      {message && <Text size="sm" role="status" className={message.ok ? 'fb-tone-ok' : 'fb-tone-err'}>{message.ok ? '✓' : '✕'} {message.text}</Text>}
      {device.interfaces.length === 0 ? (
        <Text size="sm" c="dimmed">{t('inventory.ifaces.none')}</Text>
      ) : (
        <Table.ScrollContainer minWidth={420}>
          <Table fz="sm" verticalSpacing={4} highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('inventory.ifaces.name')}</Table.Th>
                <Table.Th>{t('inventory.ifaces.type')}</Table.Th>
                <Table.Th>{t('inventory.ifaces.speed')}</Table.Th>
                <Table.Th>{t('inventory.ifaces.vlanMode')}</Table.Th>
                <Table.Th>{t('inventory.ifaces.description')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {device.interfaces.map((i) => (
                <Table.Tr key={i.id} style={i.hidden || !i.enabled ? { opacity: 0.55 } : undefined}>
                  <Table.Td ff="monospace">
                    <Group gap={4} wrap="nowrap">
                      {i.name}
                      {i.locked.length > 0 && <IconLock size={12} aria-label={t('inventory.ifaces.locked')} />}
                      {i.mgmt && <Badge size="xs" variant="outline" tt="none">{t('inventory.ifaces.mgmtShort')}</Badge>}
                    </Group>
                    {i.ips.length > 0 && <Text size="xs" c="dimmed" ff="monospace">{i.ips.join(', ')}</Text>}
                  </Table.Td>
                  <Table.Td>{i.type ? t(`inventory.ifaces.types.${i.type}`) : ''}{i.lag && <Text size="xs" c="dimmed">{i.lag}</Text>}</Table.Td>
                  <Table.Td>{speedLabel(i.speed_mbps)}</Table.Td>
                  <Table.Td>{[i.vlan, i.mode ? t(`inventory.ifaces.modes.${i.mode}`) : ''].filter(Boolean).join(' · ')}</Table.Td>
                  <Table.Td>
                    <Text size="sm" lineClamp={1}>{i.description}</Text>
                    <Group gap={4}>
                      {i.sources.map((s) => <Badge key={s} size="xs" variant="light" color="trace" tt="none">{sourceName(s)}</Badge>)}
                      {i.gone.map((s) => <Badge key={`g-${s}`} size="xs" variant="light" color="warn" tt="none">{t('inventory.gone', { source: sourceName(s) })}</Badge>)}
                      {i.hidden && <Badge size="xs" variant="outline" color="gray" tt="none">{t('inventory.hidden')}</Badge>}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    {canEdit && (
                      <Group gap={2} wrap="nowrap" justify="flex-end">
                        {i.hidden ? (
                          <Button size="compact-xs" variant="subtle" onClick={() => show.mutate(i)}>{t('inventory.unhide')}</Button>
                        ) : (
                          <>
                            <ActionIcon variant="subtle" color="gray" aria-label={t('inventory.ifaces.edit', { name: i.name, device: device.name })} onClick={() => setEditing(i)}>
                              <IconPencil size={15} />
                            </ActionIcon>
                            <ActionIcon variant="subtle" color="gray" aria-label={i.sources.length ? t('inventory.hide') : t('inventory.delete')} onClick={() => remove.mutate(i)}>
                              <IconTrash size={15} />
                            </ActionIcon>
                          </>
                        )}
                      </Group>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {editing && (
        <EditInterface device={device} iface={editing} sourceName={sourceName} onClose={() => setEditing(null)} onSaved={onChanged} />
      )}
    </Stack>
  )
}
