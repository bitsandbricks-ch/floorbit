import { Alert, Anchor, Badge, Box, Button, Group, Paper, Select, Switch, Table, Tabs, Text, TextInput, Tooltip } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconAlertTriangle, IconCategory, IconIcons, IconLock, IconPlus, IconRefresh, IconSearch } from '@tabler/icons-react'
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
import { DevicePanel } from './inventory/DevicePanel'
import { GroupPanel, type ScopeTarget } from './inventory/GroupPanel'
import { GroupTree, type GroupFilter } from './inventory/GroupTree'
import { EntriesView } from './inventory/EntriesView'
import { EntryPanel } from './inventory/EntryPanel'
import { IconLibrary } from './inventory/IconLibrary'
import { TypesEditor } from './inventory/TypesEditor'
import { DeviceIcon } from './inventory/icons'
import { effectiveLook, matches, roleIcon, statusLabel, typeName, type Draft } from './inventory/model'
import { groupAndBelow, useInventoryGroups, useInventoryTypes } from './inventory/scope'
import { LoadingState } from '@/components/ui'
import { dateTime } from '@/lib/time'

function when(iso: string, lang: string) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : dateTime(d, lang)
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
  const canManage = useCan('settings.manage')
  const [libraryOpen, library] = useDisclosure(false)
  const [typesOpen, typesEditor] = useDisclosure(false)
  const [typeTab, setTypeTab] = useState('device')
  const [entryOpen, setEntryOpen] = useState<string | null>(null)
  const types = useInventoryTypes().data?.types ?? []
  const currentType = types.find((x) => x.id === typeTab)
  const [showHidden, setShowHidden] = useState(false)
  // ?q= from the floor plan's right-click menu ("Edit seat mapping", "Show in inventory")
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.search).get('q') ?? '')
  const [role, setRole] = useState<string | null>(null)
  const [editing, setEditing] = useState<Device | null>(null)
  const [opened, setOpened] = useState<string | null>(null)
  const [scope, setScope] = useState<ScopeTarget | null>(null)
  const [group, setGroup] = useState<GroupFilter>(null)
  const [tagFilter, setTagFilter] = useState<string[]>([])
  const groupsQuery = useInventoryGroups()
  const overview = groupsQuery.data
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
    mutationFn: (changes: Partial<Draft> & { unlock?: InventoryField[]; hidden?: boolean; [k: string]: unknown }) =>
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

  const groups = overview?.groups ?? []
  const inGroup = group && group !== 'none' ? groupAndBelow(groups, group) : null
  const devices = (data?.devices ?? []).filter((d) => {
    if (!matches(d, query, role)) return false
    if (group === 'none' && d.group_id) return false
    if (inGroup && !(d.group_id && inGroup.has(d.group_id))) return false
    if (tagFilter.length) {
      const look = effectiveLook(d, groups)
      if (!tagFilter.every((tid) => look.tags.has(tid))) return false
    }
    return true
  })
  const groupName = (id?: string | null) => groups.find((g) => g.id === id)?.name ?? ''
  const tagOf = (id: string) => overview?.tags.find((x) => x.id === id)

  // A scope panel follows the saved item, so it shows what the server has now.
  const scopeNow: ScopeTarget | null = !scope || scope.kind === 'defaults' || !scope.item ? scope
    : scope.kind === 'group' ? { kind: 'group', item: groups.find((g) => g.id === scope.item?.id) ?? scope.item }
      : { kind: 'tag', item: overview?.tags.find((x) => x.id === scope.item?.id) ?? scope.item }

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
              {canManage && (
                <Button variant="default" leftSection={<IconCategory size={16} />} onClick={typesEditor.open}>
                  {t('inventory.types.open')}
                </Button>
              )}
              <Button variant="default" leftSection={<IconIcons size={16} />} onClick={library.open}>
                {t('inventory.library.open')}
              </Button>
              {!!data?.sources.length && (
                <Button variant="default" leftSection={<IconRefresh size={16} />} loading={sync.isPending} onClick={() => sync.mutate()}>
                  {t('inventory.sync')}
                </Button>
              )}
              {typeTab === 'device' && (
                <Button leftSection={<IconPlus size={16} />} onClick={() => openForm(null)}>
                  {t('inventory.add')}
                </Button>
              )}
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
      <Box className="fb-inventory-layout" style={{ display: 'grid', gap: 'var(--mantine-spacing-md)', alignItems: 'start' }}>
      {overview && (
        <GroupTree overview={overview} total={data?.devices.length ?? 0} group={group} tags={tagFilter} canEdit={canEdit}
          onGroup={setGroup} onTags={setTagFilter} onEdit={setScope} />
      )}
      <div style={{ minWidth: 0 }}>
      {types.length > 1 && (
        <Tabs value={typeTab} onChange={(v) => { setTypeTab(v ?? 'device'); setEntryOpen(null) }} mb="md">
          <Tabs.List>
            {types.map((x) => (
              <Tabs.Tab key={x.id} value={x.id} rightSection={<Badge size="xs" variant="light">{x.count}</Badge>}>
                {x.sort === 'device' ? t('inventory.types.devices') : typeName(t, x)}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>
      )}
      {typeTab !== 'device' && currentType && overview ? (
        <EntriesView key={typeTab} type={currentType} overview={overview} group={group} tags={tagFilter} canEdit={canEdit} onOpen={setEntryOpen} sourceName={sourceName} />
      ) : (<>
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
      {isPending && <LoadingState />}
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
              <Table.ScrollContainer minWidth={880}>
                <Table highlightOnHover verticalSpacing="xs" fz="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th w={36} />
                      {(['name', 'role'] as const).map((f) => (
                        <Table.Th key={f}>{t(`inventory.field.${f}`)}</Table.Th>
                      ))}
                      <Table.Th>{t('inventory.groups.one')}</Table.Th>
                      {(['model', 'mgmt_ip', 'status'] as const).map((f) => (
                        <Table.Th key={f}>{t(`inventory.field.${f}`)}</Table.Th>
                      ))}
                      <Table.Th>{t('inventory.tabs.interfaces')}</Table.Th>
                      <Table.Th>{t('inventory.fedBy')}</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {devices.map((d) => (
                      <Table.Tr key={d.id} style={d.hidden ? { opacity: 0.6 } : undefined}>
                        <Table.Td>
                          {(() => {
                            const look = effectiveLook(d, groups)
                            return <DeviceIcon icon={look.icon || roleIcon(d.role)} color={look.color} size={24} />
                          })()}
                        </Table.Td>
                        <Table.Td>
                          <Group gap={6} wrap="nowrap">
                            <Anchor component="button" type="button" fw={600} ta="left" onClick={() => setOpened(d.id)}>
                              {d.name}
                            </Anchor>
                            {!!d.blocked && (
                              <Tooltip label={t('inventory.blocks.title')}>
                                <IconAlertTriangle size={14} className="fb-tone-err" aria-label={t('inventory.blocks.title')} />
                              </Tooltip>
                            )}
                            {d.locked.length > 0 && (
                              <Tooltip label={d.locked.map((f) => t(`inventory.field.${f}`)).join(', ')}>
                                <IconLock size={14} aria-label={d.locked.map((f) => t(`inventory.field.${f}`)).join(', ')} />
                              </Tooltip>
                            )}
                          </Group>
                          <Group gap={4}>
                            <Text size="xs" c="dimmed">
                              {d.placed ? t('inventory.placed') : t('inventory.notPlaced')}
                            </Text>
                            {(d.tags ?? []).map((tid) => tagOf(tid) && (
                              <Badge key={tid} size="xs" tt="none" variant="light" color={tagOf(tid)?.color || 'gray'}>{tagOf(tid)?.name}</Badge>
                            ))}
                          </Group>
                        </Table.Td>
                        <Table.Td>{t(`inventory.role.${d.role}`, { defaultValue: d.role })}</Table.Td>
                        <Table.Td>{groupName(d.group_id)}</Table.Td>
                        <Table.Td>{d.model}</Table.Td>
                        <Table.Td ff="monospace">{d.mgmt_ip}</Table.Td>
                        <Table.Td>{statusLabel(t, d.status)}</Table.Td>
                        <Table.Td>{d.interface_count || ''}</Table.Td>
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
      </>)}
      </div>
      </Box>

      {opened && overview && (
        <DevicePanel key={opened} id={opened} overview={overview} sourceName={sourceName} onClose={() => setOpened(null)}
          onEdit={() => {
            const d = data?.devices.find((x) => x.id === opened)
            if (d) openForm(d)
          }} />
      )}
      {scopeNow && overview && (
        <GroupPanel key={scopeNow.kind === 'defaults' ? 'defaults' : `${scopeNow.kind}-${scopeNow.item?.id ?? 'new'}`} target={scopeNow}
          overview={overview} onClose={() => setScope(null)} onSaved={setScope} />
      )}
      {formOpen && data && (
        <DeviceForm
          key={editing?.id ?? 'new'}
          device={editing}
          roles={data.roles}
          overview={overview}
          sourceName={sourceName}
          opened={formOpen}
          busy={save.isPending}
          error={formError}
          onClose={form.close}
          onSave={(changes) => save.mutate(changes)}
          onUnlock={(f) => save.mutate({ unlock: [f] })}
        />
      )}
      <>
        <IconLibrary opened={libraryOpen} canManage={canManage} onClose={library.close} />
      {entryOpen && currentType && overview && (
        <EntryPanel key={`${typeTab}-${entryOpen}`} type={currentType} id={entryOpen} overview={overview} canEdit={canEdit} onClose={() => setEntryOpen(null)} />
      )}
      {typesOpen && overview && <TypesEditor opened={typesOpen} overview={overview} start={typeTab} onClose={typesEditor.close} />}
      </>
    </Layout>
  )
}
