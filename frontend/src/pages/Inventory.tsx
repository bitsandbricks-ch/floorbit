import {
  ActionIcon, Alert, Anchor, Badge, Box, Button, Chip, Group, Menu, Modal, MultiSelect, Pagination, Paper, Select, Switch, Table, Tabs, Text,
  TextInput, Tooltip, UnstyledButton,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import {
  IconAlertTriangle, IconCategory, IconChevronDown, IconChevronUp, IconDots, IconIcons, IconLock, IconMapPin, IconPlus, IconRefresh, IconSearch,
} from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { del, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useInventory } from '@/api/queries'
import type { Device, InventoryField, InventorySource, SyncReport } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { DeviceForm } from './inventory/DeviceForm'
import type { ScopeTarget } from './inventory/ScopeEditor'
import { GroupTree, type GroupFilter } from './inventory/GroupTree'
import { EntriesView } from './inventory/EntriesView'
import { IconLibrary } from './inventory/IconLibrary'
import { TypesEditor } from './inventory/TypesEditor'
import { DeviceIcon } from './inventory/icons'
import { devicePath, effectiveLook, entryPath, matches, roleIcon, scopePath, typeName, type Draft } from './inventory/model'
import { groupAndBelow, groupTree, useInventoryGroups, useInventoryTypes } from './inventory/scope'
import { LoadingState } from '@/components/ui'
import { dateTime } from '@/lib/time'

const PAGE = 50
const BIT: Record<string, string> = { online: '', offline: 'is-down', unknown: 'is-off' }
type SortKey = 'name' | 'role' | 'group' | 'model' | 'mgmt_ip' | 'ports'

function portsText(d: Device) {
  if (d.ports) return `${d.ports.up}/${d.ports.total}`
  return d.interface_count ? String(d.interface_count) : '–'
}

/** Natural order for names and addresses (sw-2 before sw-10, 198.51.100.9 before .10). */
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

function sortDevices(list: Device[], sort: { key: SortKey; desc: boolean }, groups: { id: string; name: string }[]) {
  const value = (d: Device): string | number => {
    if (sort.key === 'group') return groups.find((g) => g.id === d.group_id)?.name ?? ''
    if (sort.key === 'ports') return d.ports ? d.ports.up / Math.max(1, d.ports.total) : -1
    return d[sort.key] ?? ''
  }
  const out = [...list].sort((a, b) => {
    const x = value(a), y = value(b)
    return typeof x === 'number' && typeof y === 'number' ? x - y : collator.compare(String(x), String(y))
  })
  return sort.desc ? out.reverse() : out
}

/** Where the inventory comes from and when it last synced, as one small chip: red when a sync failed. */
function SyncChip({ sources, every }: { sources: InventorySource[]; every?: number | null }) {
  const { t, i18n } = useTranslation()
  if (!sources.length) {
    return (
      <Tooltip label={t('inventory.noSources')} multiline w={280}>
        <Badge variant="default" tt="none" ml="auto">{t('inventory.manualOnly')}</Badge>
      </Tooltip>
    )
  }
  const failed = sources.filter((s) => s.last_sync?.error)
  const latest = sources.map((s) => s.last_sync?.at).filter(Boolean).sort().pop()
  const label = failed.length ? t('inventory.syncFailedShort', { source: failed.map((s) => s.name).join(', ') })
    : latest ? t('inventory.syncedAgo', { source: sources.map((s) => s.name).join(', '), when: ago(latest, i18n.language) })
      : t('inventory.neverSyncedShort', { source: sources.map((s) => s.name).join(', ') })
  const detail = [...sources.map((s) => `${s.name}: ${s.last_sync?.error ?? (s.last_sync ? when(s.last_sync.at, i18n.language) : t('inventory.neverSynced'))}`),
    every ? t('inventory.syncEvery', { minutes: every }) : ''].filter(Boolean).join('\n')
  return (
    <Tooltip label={<span style={{ whiteSpace: 'pre-line' }}>{detail}</span>} multiline w={320}>
      <Badge variant="light" color={failed.length ? 'down' : 'gray'} tt="none" ml="auto" role="status">{label}</Badge>
    </Tooltip>
  )
}

function when(iso: string, lang: string) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : dateTime(d, lang)
}

function ago(iso: string, lang: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  const fmt = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })
  return s < 3600 ? fmt.format(-Math.round(s / 60), 'minute') : s < 86400 ? fmt.format(-Math.round(s / 3600), 'hour') : when(iso, lang)
}

export default function Inventory() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const canManage = useCan('settings.manage')
  const [libraryOpen, library] = useDisclosure(false)
  const [typesOpen, typesEditor] = useDisclosure(false)
  const navigate = useNavigate()
  // ?type= from an entry's page going back to its list
  const [typeTab, setTypeTab] = useState(() => new URLSearchParams(window.location.search).get('type') ?? 'device')
  const types = useInventoryTypes().data?.types ?? []
  const currentType = types.find((x) => x.id === typeTab)
  const [showHidden, setShowHidden] = useState(false)
  // ?q= from the floor plan's right-click menu ("Edit seat mapping", "Show in inventory")
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.search).get('q') ?? '')
  const [role, setRole] = useState<string | null>(null)
  const [editing, setEditing] = useState<Device | null>(null)
  const [group, setGroup] = useState<GroupFilter>(null)
  const [tagFilter, setTagFilter] = useState<string[]>([])
  const [state, setState] = useState<string | null>(null)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'name', desc: false })
  const [page, setPage] = useState(1)
  const [removing, setRemoving] = useState<Device | null>(null)
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
  const all = data?.devices ?? []
  // Everything but the role picks the rows, so the role chips can count what the other filters leave.
  const filtered = all.filter((d) => {
    if (!matches(d, query, null)) return false
    if (group === 'none' && d.group_id) return false
    if (inGroup && !(d.group_id && inGroup.has(d.group_id))) return false
    if (state && (d.state ?? 'unknown') !== state) return false
    if (tagFilter.length) {
      const look = effectiveLook(d, groups)
      if (!tagFilter.every((tid) => look.tags.has(tid))) return false
    }
    return true
  })
  const roleCounts = new Map<string, number>()
  for (const d of filtered) roleCounts.set(d.role, (roleCounts.get(d.role) ?? 0) + 1)
  const devices = sortDevices(filtered.filter((d) => !role || d.role === role), sort, groups)
  const pages = Math.max(1, Math.ceil(devices.length / PAGE))
  const shown = devices.slice((Math.min(page, pages) - 1) * PAGE, Math.min(page, pages) * PAGE)
  const groupName = (id?: string | null) => groups.find((g) => g.id === id)?.name ?? ''
  const tagOf = (id: string) => overview?.tags.find((x) => x.id === id)
  const otherTypes = types.filter((x) => x.sort !== 'device' && x.count > 0)
  const deviceCount = types.find((x) => x.sort === 'device')?.count ?? all.length
  const sortBy = (key: SortKey) => { setSort((s) => ({ key, desc: s.key === key ? !s.desc : false })); setPage(1) }
  const th = (key: SortKey, label: string) => (
    <Table.Th aria-sort={sort.key === key ? (sort.desc ? 'descending' : 'ascending') : undefined}>
      <UnstyledButton onClick={() => sortBy(key)} className="fb-sort">
        {label}{sort.key === key && (sort.desc ? <IconChevronDown size={12} /> : <IconChevronUp size={12} />)}
      </UnstyledButton>
    </Table.Th>
  )

  // Groups, tags and the defaults have their own pages.
  const openScope = (target: ScopeTarget) => navigate(
    target.kind === 'defaults' ? '/inventory/defaults'
      : target.item ? scopePath(target.kind, target.item.id)
        : target.kind === 'group' ? `/inventory/groups/new${target.parent ? `?parent=${encodeURIComponent(target.parent)}` : ''}` : '/inventory/tags/new')

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
              {typeTab === 'device' && (
                <Button leftSection={<IconPlus size={16} />} onClick={() => openForm(null)}>
                  {t('inventory.add')}
                </Button>
              )}
              <Menu position="bottom-end">
                <Menu.Target>
                  <ActionIcon variant="default" size="lg" aria-label={t('inventory.more')}><IconDots size={18} /></ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  {canManage && <Menu.Item leftSection={<IconCategory size={16} />} onClick={typesEditor.open}>{t('inventory.types.open')}</Menu.Item>}
                  <Menu.Item leftSection={<IconIcons size={16} />} onClick={library.open}>{t('inventory.library.open')}</Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </>
          )
        }
      />
      <Tabs value={typeTab} onChange={(v) => { setTypeTab(v ?? 'device'); setPage(1) }} mb="md">
        <Tabs.List>
          <Tabs.Tab value="device" rightSection={<Text span size="xs" c="dimmed">{deviceCount}</Text>}>{t('inventory.types.devices')}</Tabs.Tab>
          {otherTypes.map((x) => (
            <Tabs.Tab key={x.id} value={x.id} rightSection={<Text span size="xs" c="dimmed">{x.count}</Text>}>{typeName(t, x)}</Tabs.Tab>
          ))}
          <Tabs.Tab value="groups">{t('inventory.groupsAndTags')}</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      <Text size="sm" role="status" mb={message || sync.isPending ? 'sm' : 0} className={message ? (message.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {sync.isPending ? t('inventory.syncing') : message ? `${message.ok ? '✓' : '✕'} ${message.text}` : ''}
      </Text>
      {typeTab === 'groups' && overview ? (
        <Box maw={520}>
          <GroupTree overview={overview} total={all.length} group={group} tags={tagFilter} canEdit={canEdit}
            onGroup={(g) => { setGroup(g); setTypeTab('device'); setPage(1) }}
            onTags={(tg) => { setTagFilter(tg); setTypeTab('device'); setPage(1) }} onEdit={openScope} />
        </Box>
      ) : typeTab !== 'device' && currentType && overview ? (
        <EntriesView key={typeTab} type={currentType} overview={overview} group={group} tags={tagFilter} canEdit={canEdit} onOpen={(id) => navigate(entryPath(typeTab, id))} sourceName={sourceName} />
      ) : (<>
      <Group gap="sm" mb="sm" wrap="wrap">
        <TextInput
          aria-label={t('inventory.search')}
          placeholder={t('inventory.searchPlaceholder')}
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(e) => { setQuery(e.currentTarget.value); setPage(1) }}
          style={{ flex: '1 1 240px', maxWidth: 360 }}
        />
        <Select aria-label={t('inventory.groups.one')} placeholder={t('inventory.anyGroup')} clearable w={170}
          data={[...groupTree(groups).map(({ group: g, depth }) => ({ value: g.id, label: `${'  '.repeat(depth)}${g.name}` })),
            ...(groups.length ? [{ value: 'none', label: t('inventory.groups.none') }] : [])]}
          value={group} onChange={(v) => { setGroup(v); setPage(1) }} />
        {!!overview?.tags.length && (
          <MultiSelect aria-label={t('inventory.tags.label')} placeholder={tagFilter.length ? undefined : t('inventory.anyTag')} clearable w={200}
            data={overview.tags.map((x) => ({ value: x.id, label: x.name }))} value={tagFilter} onChange={(v) => { setTagFilter(v); setPage(1) }} />
        )}
        <Select aria-label={t('inventory.state.label')} placeholder={t('inventory.state.any')} clearable w={150}
          data={(['online', 'offline', 'unknown'] as const).map((v) => ({ value: v, label: t(`inventory.state.${v}`) }))}
          value={state} onChange={(v) => { setState(v); setPage(1) }} />
        <Switch label={t('inventory.showHidden')} checked={showHidden} onChange={(e) => setShowHidden(e.currentTarget.checked)} />
        {data && <SyncChip sources={data.sources} every={data.every} />}
      </Group>
      {data && filtered.length > 0 && (
        <Chip.Group value={role ?? ''} onChange={(v) => { setRole((v as string) || null); setPage(1) }}>
          <Group gap={6} mb="sm">
            <Chip value="" size="sm" variant="outline">{t('inventory.allCount', { count: filtered.length })}</Chip>
            {[...roleCounts.entries()].sort((a, b) => b[1] - a[1]).map(([r, n]) => (
              <Chip key={r} value={r} size="sm" variant="outline">{`${t(`inventory.role.${r}`, { defaultValue: r })} ${n}`}</Chip>
            ))}
          </Group>
        </Chip.Group>
      )}
      {isPending && <LoadingState />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data && (
        devices.length === 0 ? (
          <Text c="dimmed">{data.devices.length ? t('inventory.noMatch') : t('inventory.empty')}</Text>
        ) : (
          <>
            <Paper withBorder>
              <Table.ScrollContainer minWidth={860}>
                <Table highlightOnHover verticalSpacing={8} fz="sm" className="fb-inventory-table">
                  <Table.Thead>
                    <Table.Tr>
                      {th('name', t('inventory.field.name'))}
                      {th('role', t('inventory.field.role'))}
                      {th('group', t('inventory.groups.one'))}
                      {th('model', t('inventory.field.model'))}
                      {th('mgmt_ip', t('inventory.field.mgmt_ip'))}
                      {th('ports', t('inventory.ports'))}
                      <Table.Th>{t('inventory.fedBy')}</Table.Th>
                      <Table.Th w={44} />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {shown.map((d) => {
                      const look = effectiveLook(d, groups)
                      return (
                        <Table.Tr key={d.id} style={d.hidden ? { opacity: 0.6 } : undefined}>
                          <Table.Td>
                            <Group gap={8} wrap="nowrap">
                              <Tooltip label={t(`inventory.state.${d.state ?? 'unknown'}`)}>
                                <span className={`fb-bit ${BIT[d.state ?? 'unknown']}`} aria-label={t(`inventory.state.${d.state ?? 'unknown'}`)} />
                              </Tooltip>
                              <DeviceIcon icon={look.icon || roleIcon(d.role)} color={look.color} size={20} />
                              <Anchor component={Link} to={devicePath(d.id)} fw={600}>{d.name}</Anchor>
                              {d.placed && (
                                <Tooltip label={t('inventory.placed')}>
                                  <IconMapPin size={14} className="fb-dim" aria-label={t('inventory.placed')} />
                                </Tooltip>
                              )}
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
                              {(d.tags ?? []).map((tid) => tagOf(tid) && (
                                <Badge key={tid} size="xs" tt="none" variant="light" color={tagOf(tid)?.color || 'gray'}>{tagOf(tid)?.name}</Badge>
                              ))}
                            </Group>
                          </Table.Td>
                          <Table.Td>{t(`inventory.role.${d.role}`, { defaultValue: d.role })}</Table.Td>
                          <Table.Td>{groupName(d.group_id)}</Table.Td>
                          <Table.Td>{d.model}</Table.Td>
                          <Table.Td ff="monospace">{d.mgmt_ip}</Table.Td>
                          <Table.Td ff="monospace">{portsText(d)}</Table.Td>
                          <Table.Td>
                            <Group gap={4} wrap="nowrap">
                              {d.sources.length === 0 && <Badge variant="outline" color="gray" tt="none">{t('inventory.manual')}</Badge>}
                              {d.sources.map((src) => <Badge key={src} variant="light" color="trace" tt="none">{sourceName(src)}</Badge>)}
                              {d.gone.map((src) => <Badge key={`gone-${src}`} variant="light" color="warn" tt="none">{t('inventory.gone', { source: sourceName(src) })}</Badge>)}
                              {d.hidden && <Badge variant="outline" color="gray" tt="none">{t('inventory.hidden')}</Badge>}
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            <Menu position="bottom-end">
                              <Menu.Target>
                                <ActionIcon variant="subtle" color="gray" aria-label={t('inventory.rowMenu', { name: d.name })}><IconDots size={16} /></ActionIcon>
                              </Menu.Target>
                              <Menu.Dropdown>
                                <Menu.Item component={Link} to={devicePath(d.id)}>{t('inventory.open')}</Menu.Item>
                                {canEdit && (d.hidden
                                  ? <Menu.Item onClick={() => unhide.mutate(d)}>{t('inventory.unhide')}</Menu.Item>
                                  : <Menu.Item color="down" onClick={() => setRemoving(d)}>{d.sources.length ? t('inventory.hide') : t('inventory.delete')}</Menu.Item>)}
                              </Menu.Dropdown>
                            </Menu>
                          </Table.Td>
                        </Table.Tr>
                      )
                    })}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Paper>
            <Group justify="space-between" mt="sm">
              <Text size="sm" c="dimmed">{t('inventory.count', { count: devices.length })}</Text>
              {pages > 1 && <Pagination size="sm" total={pages} value={Math.min(page, pages)} onChange={setPage} />}
            </Group>
          </>
        )
      )}
      </>)}
      <Modal opened={!!removing} onClose={() => setRemoving(null)} centered
        title={removing?.sources.length ? t('inventory.hide') : t('inventory.delete')}>
        {removing && (
          <>
            <Text mb="lg">
              {removing.sources.length
                ? t('inventory.deleteFed', { name: removing.name, source: sourceName(removing.sources[0]) })
                : t('inventory.deleteManual', { name: removing.name })}
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setRemoving(null)}>{t('common.cancel')}</Button>
              <Button color="down" onClick={() => { remove.mutate(removing); setRemoving(null) }}>{t('common.confirm')}</Button>
            </Group>
          </>
        )}
      </Modal>

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
      {typesOpen && overview && <TypesEditor opened={typesOpen} overview={overview} start={typeTab} onClose={typesEditor.close} />}
      </>
    </Layout>
  )
}
