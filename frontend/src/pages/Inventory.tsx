import { Alert, Anchor, Badge, Button, Group, Loader, Paper, Select, Switch, Table, Text, TextInput, Tooltip } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconLock, IconPlus, IconRefresh, IconSearch } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useInventory } from '@/api/queries'
import type { Device, InventoryField, InventorySource, SyncReport } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { DeviceForm } from './inventory/DeviceForm'
import { matches, type Draft } from './inventory/model'

function when(iso: string, lang: string) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(lang, { dateStyle: 'short', timeStyle: 'short' })
}

function SourceLine({ source }: { source: InventorySource }) {
  const { t, i18n } = useTranslation()
  const last = source.last_sync
  return (
    <Text size="sm" c={last?.error ? undefined : 'dimmed'} className={last?.error ? 'fb-tone-err' : undefined}>
      <strong>{source.name}</strong>:{' '}
      {!last
        ? t('inventory.neverSynced')
        : last.error
          ? t('inventory.syncFailed', { error: last.error })
          : t('inventory.lastSync', { when: when(last.at, i18n.language) })}
    </Text>
  )
}

export default function Inventory() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const [showHidden, setShowHidden] = useState(false)
  const [query, setQuery] = useState('')
  const [role, setRole] = useState<string | null>(null)
  const [editing, setEditing] = useState<Device | null>(null)
  const [formOpen, form] = useDisclosure(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const { data, error, isPending } = useInventory(showHidden)

  const sourceName = useMemo(() => {
    const names = Object.fromEntries((data?.sources ?? []).map((s) => [s.id, s.name]))
    return (id: string) => names[id] ?? id
  }, [data])

  const refresh = () => client.invalidateQueries({ queryKey: qk.inventoryAll })

  const save = useMutation({
    mutationFn: (changes: Partial<Draft> & { unlock?: InventoryField[]; hidden?: boolean }) =>
      editing ? patch<Device>(`/api/inventory/${encodeURIComponent(editing.id)}`, changes) : post<Device>('/api/inventory', changes),
    onSuccess: (device, changes) => {
      void refresh()
      setFormError(null)
      if ('unlock' in changes) {
        setEditing(device)
        return
      }
      form.close()
      setMessage({ ok: true, text: t('inventory.saved') })
    },
    onError: (e) => setFormError(e.message),
  })
  const remove = useMutation({
    mutationFn: (device: Device) => del<{ result: string }>(`/api/inventory/${encodeURIComponent(device.id)}`),
    onSuccess: () => void refresh(),
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const unhide = useMutation({
    mutationFn: (device: Device) => patch<Device>(`/api/inventory/${encodeURIComponent(device.id)}`, { hidden: false }),
    onSuccess: () => void refresh(),
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const sync = useMutation({
    mutationFn: () => post<{ reports: SyncReport[] }>('/api/inventory/sync'),
    onSuccess: ({ reports }) => {
      void refresh()
      const failed = reports.filter((r) => r.error)
      const sum = (k: keyof SyncReport) => reports.reduce((n, r) => n + (Number(r[k]) || 0), 0)
      setMessage(
        failed.length
          ? { ok: false, text: failed.map((r) => `${sourceName(r.plugin)}: ${r.error}`).join('; ') }
          : { ok: true, text: t('inventory.syncDone', { added: sum('added'), updated: sum('updated'), gone: sum('gone'), locked: sum('locked') }) },
      )
    },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })

  const devices = (data?.devices ?? []).filter((d) => matches(d, query, role))

  function openForm(device: Device | null) {
    setEditing(device)
    setFormError(null)
    form.open()
  }

  return (
    <Layout title={t('inventory.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead
        title={t('inventory.title')}
        desc={t('inventory.intro')}
        actions={
          canEdit && (
            <>
              {!!data?.sources.length && (
                <Button variant="default" leftSection={<IconRefresh size={16} />} loading={sync.isPending} onClick={() => sync.mutate()}>
                  {t('inventory.sync')}
                </Button>
              )}
              <Button leftSection={<IconPlus size={16} />} onClick={() => openForm(null)}>
                {t('inventory.add')}
              </Button>
            </>
          )
        }
      />
      {data && (
        <Paper withBorder radius="lg" p="sm" mb="md">
          {data.sources.length ? (
            data.sources.map((s) => <SourceLine key={s.id} source={s} />)
          ) : (
            <Text size="sm" c="dimmed">
              {t('inventory.noSources')} <Anchor href="/settings/plugins">{t('common.plugins')}</Anchor>
            </Text>
          )}
        </Paper>
      )}
      <Text size="sm" role="status" mb="sm" className={message ? (message.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {sync.isPending ? t('inventory.syncing') : message ? `${message.ok ? '✓' : '✕'} ${message.text}` : ''}
      </Text>
      <Group gap="sm" mb="md" wrap="wrap" align="flex-end">
        <TextInput
          label={t('inventory.search')}
          placeholder={t('inventory.searchPlaceholder')}
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
          style={{ flex: '1 1 260px' }}
        />
        <Select
          label={t('inventory.field.role')}
          placeholder={t('inventory.allRoles')}
          data={(data?.roles ?? []).map((r) => ({ value: r, label: t(`inventory.role.${r}`, { defaultValue: r }) }))}
          value={role}
          onChange={setRole}
          clearable
          w={200}
        />
        <Switch label={t('inventory.showHidden')} checked={showHidden} onChange={(e) => setShowHidden(e.currentTarget.checked)} mb={8} />
      </Group>
      {isPending && <Loader aria-label={t('common.loading')} />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data && (
        <>
          <Text size="sm" c="dimmed" mb="xs">
            {t('inventory.count', { count: devices.length })}
          </Text>
          {devices.length === 0 ? (
            <Text>{data.devices.length ? t('inventory.noMatch') : t('inventory.empty')}</Text>
          ) : (
            <Paper withBorder radius="lg">
              <Table.ScrollContainer minWidth={760}>
                <Table highlightOnHover verticalSpacing="xs" fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      {(['name', 'role', 'model', 'mgmt_ip', 'hall', 'status'] as const).map((f) => (
                        <Table.Th key={f}>{t(`inventory.field.${f}`)}</Table.Th>
                      ))}
                      <Table.Th>{t('inventory.fedBy')}</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {devices.map((d) => (
                      <Table.Tr key={d.id} style={d.hidden ? { opacity: 0.6 } : undefined}>
                        <Table.Td>
                          <Group gap={6} wrap="nowrap">
                            {canEdit ? (
                              <Anchor component="button" type="button" fw={600} ta="left" onClick={() => openForm(d)}>
                                {d.name}
                              </Anchor>
                            ) : (
                              <Text fw={600} size="sm">
                                {d.name}
                              </Text>
                            )}
                            {d.locked.length > 0 && (
                              <Tooltip label={d.locked.map((f) => t(`inventory.field.${f}`)).join(', ')}>
                                <IconLock size={14} aria-label={d.locked.map((f) => t(`inventory.field.${f}`)).join(', ')} />
                              </Tooltip>
                            )}
                          </Group>
                          <Text size="xs" c="dimmed">
                            {d.placed ? t('inventory.placed') : t('inventory.notPlaced')}
                          </Text>
                        </Table.Td>
                        <Table.Td>{t(`inventory.role.${d.role}`, { defaultValue: d.role })}</Table.Td>
                        <Table.Td>{d.model}</Table.Td>
                        <Table.Td ff="monospace">{d.mgmt_ip}</Table.Td>
                        <Table.Td>{d.hall}</Table.Td>
                        <Table.Td>{d.status}</Table.Td>
                        <Table.Td>
                          <Group gap={4}>
                            {d.sources.length === 0 && (
                              <Badge variant="outline" color="gray" tt="none">
                                {t('inventory.manual')}
                              </Badge>
                            )}
                            {d.sources.map((s) => (
                              <Badge key={s} variant="light" color="trace" tt="none">
                                {sourceName(s)}
                              </Badge>
                            ))}
                            {d.gone.map((s) => (
                              <Badge key={`gone-${s}`} variant="light" color="warn" tt="none">
                                {t('inventory.gone', { source: sourceName(s) })}
                              </Badge>
                            ))}
                            {d.hidden && (
                              <Badge variant="outline" color="gray" tt="none">
                                {t('inventory.hidden')}
                              </Badge>
                            )}
                          </Group>
                        </Table.Td>
                        <Table.Td>
                          {canEdit &&
                            (d.hidden ? (
                              <Button size="xs" variant="subtle" onClick={() => unhide.mutate(d)}>
                                {t('inventory.unhide')}
                              </Button>
                            ) : (
                              <ConfirmButton
                                size="xs"
                                variant="subtle"
                                danger
                                label={d.sources.length ? t('inventory.hide') : t('inventory.delete')}
                                question={
                                  d.sources.length
                                    ? t('inventory.deleteFed', { name: d.name, source: sourceName(d.sources[0]) })
                                    : t('inventory.deleteManual', { name: d.name })
                                }
                                onConfirm={() => remove.mutate(d)}
                              />
                            ))}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Paper>
          )}
        </>
      )}
      {formOpen && data && (
        <DeviceForm
          key={editing?.id ?? 'new'}
          device={editing}
          roles={data.roles}
          sourceName={sourceName}
          opened={formOpen}
          busy={save.isPending}
          error={formError}
          onClose={form.close}
          onSave={(changes) => save.mutate(changes)}
          onUnlock={(f) => save.mutate({ unlock: [f] })}
        />
      )}
    </Layout>
  )
}
