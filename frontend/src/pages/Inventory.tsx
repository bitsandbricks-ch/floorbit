import {
  ActionIcon, Alert, Anchor, Badge, Box, Button, Chip, Group, Menu, Modal, Tabs, Text,
  Tooltip,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import {
  IconAlertTriangle, IconCategory, IconDots, IconIcons, IconLock, IconMapPin, IconPlus, IconRefresh, IconTags,
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
import { DataTable, FilterBar, LoadingState, PageHead, useFilters } from '@bitsandbricks/ui'
import { useDriftAll } from '@/api/inventoryDrift'
import { DeviceForm } from './inventory/DeviceForm'
import { DriftAll } from './inventory/DriftPanel'
import { IpamView } from './inventory/IpamView'
import { UnknownSenders } from './inventory/UnknownSenders'
import { ipamSubOf, type IpamSub } from './inventory/ipam'
import type { ScopeTarget } from './inventory/ScopeEditor'
import { GroupTree, type GroupFilter } from './inventory/GroupTree'
import { EntriesView } from './inventory/EntriesView'
import { IconLibrary } from './inventory/IconLibrary'
import { TypesEditor } from './inventory/TypesEditor'
import { DeviceIcon } from './inventory/icons'
import { LastDayCell, UplinkCell } from './inventory/ListCells'
import { PickBar } from './inventory/PickBar'
import { lastDaySort, uplinkSort, useAgentName } from './inventory/listColumns'
import { devicePath, effectiveLook, entryPath, matches, roleIcon, scopePath, typeName, type Draft } from './inventory/model'
import { groupAndBelow, groupTree, useInventoryGroups, useInventoryTypes } from './inventory/scope'
import { dateTime } from '@/lib/time'

/** Types with a tab of their own next to Inventory (Cables, Electrics): not again in the type tabs. */
const ON_HUB_TABS = new Set(['cable', 'circuit', 'power-board'])

const BIT: Record<string, string> = { online: '', offline: 'is-down', unknown: 'is-off' }

function portsText(d: Device) {
  if (d.ports) return `${d.ports.up}/${d.ports.total}`
  return d.interface_count ? String(d.interface_count) : '–'
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
  const canRun = useCan('ports.act')
  const [libraryOpen, library] = useDisclosure(false)
  const [typesOpen, typesEditor] = useDisclosure(false)
  const navigate = useNavigate()
  // ?type= from an entry's page going back to its list
  const [typeTab, setTypeTab] = useState(() => {
    const type = new URLSearchParams(window.location.search).get('type') ?? 'device'
    return ipamSubOf(type) ? 'ipam' : type
  })
  // VLANs and prefixes live on the IPAM tab (#1346); ?type=vlan|prefix comes back from their pages.
  const [ipamSub, setIpamSub] = useState<IpamSub>(() => ipamSubOf(new URLSearchParams(window.location.search).get('type') ?? '') ?? 'prefixes')
  const types = useInventoryTypes().data?.types ?? []
  const currentType = types.find((x) => x.id === typeTab)
  // The shared filter row, kept in the address (#982): ?q= also comes from the floor plan's
  // right-click menu ("Show in inventory"), ?view=drift is every device that differs (#903).
  const filters = useFilters({ role: '', group: '', tag: '', state: '', hidden: '', view: '' })
  const query = filters.search
  const role = filters.values.role || null
  const group: GroupFilter = filters.values.group || null
  const setGroup = (g: GroupFilter) => filters.set('group', g ?? '')
  const tagFilter = filters.values.tag ? [filters.values.tag] : []
  const setTagFilter = (tags: string[]) => filters.set('tag', tags[tags.length - 1] ?? '')
  const state = filters.values.state || null
  const showHidden = filters.values.hidden === 'shown'
  const driftView = filters.values.view === 'drift'
  const setDriftView = (on: boolean) => filters.set('view', on ? 'drift' : '')
  const [editing, setEditing] = useState<Device | null>(null)
  const agentName = useAgentName()
  const driftAll = useDriftAll(driftView)
  const [removing, setRemoving] = useState<Device | null>(null)
  const [picks, setPicks] = useState<string[]>([])
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
  const devices = filtered.filter((d) => !role || d.role === role)
  // Only what the filters still show is acted on: a pick hidden by a filter would surprise.
  const picked = devices.filter((d) => picks.includes(d.id))
  const driftCount = all.filter((d) => d.drift).length
  const groupName = (id?: string | null) => groups.find((g) => g.id === id)?.name ?? ''
  const tagOf = (id: string) => overview?.tags.find((x) => x.id === id)
  // Cables and power have tabs of their own above (Cables, Electrics): one row of tabs, not two (#1426).
  const otherTypes = types.filter((x) => x.sort !== 'device' && x.count > 0 && !ipamSubOf(x.id) && !ON_HUB_TABS.has(x.id))
  const ipamCount = types.filter((x) => ipamSubOf(x.id)).reduce((n, x) => n + x.count, 0)
  const deviceCount = types.find((x) => x.sort === 'device')?.count ?? all.length
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
                  <Menu.Item leftSection={<IconTags size={16} />} component={Link} to="/inventory/properties">{t('inventory.propCatalog.open')}</Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </>
          )
        }
      />
      <Tabs value={typeTab} onChange={(v) => { setTypeTab(v ?? 'device') }} mb="md">
        <Tabs.List>
          <Tabs.Tab value="device" rightSection={<Text span size="xs" c="dimmed">{deviceCount}</Text>}>{t('inventory.types.devices')}</Tabs.Tab>
          {otherTypes.map((x) => (
            <Tabs.Tab key={x.id} value={x.id} rightSection={<Text span size="xs" c="dimmed">{x.count}</Text>}>{typeName(t, x)}</Tabs.Tab>
          ))}
          <Tabs.Tab value="ipam" rightSection={<Text span size="xs" c="dimmed">{ipamCount}</Text>}>{t('ipam.title')}</Tabs.Tab>
          <Tabs.Tab value="groups">{t('inventory.groupsAndTags')}</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      <Text size="sm" role="status" mb={message || sync.isPending ? 'sm' : 0} className={message ? (message.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {sync.isPending ? t('inventory.syncing') : message ? `${message.ok ? '✓' : '✕'} ${message.text}` : ''}
      </Text>
      {typeTab === 'groups' && overview ? (
        <Box maw={520}>
          <GroupTree overview={overview} total={all.length} group={group} tags={tagFilter} canEdit={canEdit}
            onGroup={(g) => { setGroup(g); setTypeTab('device') }}
            onTags={(tg) => { setTagFilter(tg); setTypeTab('device') }} onEdit={openScope} />
        </Box>
      ) : typeTab === 'ipam' ? (
        <IpamView types={types} sub={ipamSub} onSub={setIpamSub} canEdit={canEdit} sourceName={sourceName} />
      ) : typeTab !== 'device' && currentType && overview ? (
        <EntriesView key={typeTab} type={currentType} overview={overview} group={group} tags={tagFilter} canEdit={canEdit} onOpen={(id) => navigate(entryPath(typeTab, id))} sourceName={sourceName} />
      ) : (<>
      <FilterBar search={filters.search} onSearchChange={filters.setSearch} searchLabel={t('inventory.searchPlaceholder')} onClear={filters.clear}
        groups={filters.groups([
          { key: 'role', label: t('inventory.field.role'), hidden: driftView || roleCounts.size < 2, options: [
            { value: '', label: t('inventory.anyRole'), count: filtered.length },
            ...[...roleCounts.entries()].sort((a, b) => b[1] - a[1])
              .map(([r, n]) => ({ value: r, label: t(`inventory.role.${r}`, { defaultValue: r }), count: n }))] },
          { key: 'group', label: t('inventory.groups.one'), hidden: !groups.length, options: [
            { value: '', label: t('inventory.anyGroup') },
            ...groupTree(groups).map(({ group: g, depth }) => ({ value: g.id, label: `${'\u00a0\u00a0'.repeat(depth)}${g.name}`, text: g.name })),
            { value: 'none', label: t('inventory.groups.none') }] },
          { key: 'tag', label: t('inventory.tags.label'), hidden: !overview?.tags.length, options: [
            { value: '', label: t('inventory.anyTag') }, ...(overview?.tags ?? []).map((x) => ({ value: x.id, label: x.name }))] },
          { key: 'state', label: t('inventory.state.label'), options: [
            { value: '', label: t('inventory.state.any') },
            ...(['online', 'offline', 'unknown'] as const).map((v) => ({ value: v, label: t(`inventory.state.${v}`),
              count: all.filter((d) => (d.state ?? 'unknown') === v).length }))] },
          { key: 'hidden', label: t('inventory.hiddenLabel'), options: [
            { value: '', label: t('inventory.hiddenOff') }, { value: 'shown', label: t('inventory.hiddenOn') }] },
        ])}
        actions={(
          <>
            {(driftCount > 0 || driftView) && (
              <Chip size="sm" color="warn" variant="outline" checked={driftView} onChange={setDriftView}>
                {`${t('inventoryDrift.filter')} ${driftCount}`}
              </Chip>
            )}
            {data && <SyncChip sources={data.sources} every={data.every} />}
            {data && <UnknownSenders canEdit={canEdit} roles={data.roles} />}
          </>
        )} />
      {isPending && <LoadingState rows={3} />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {driftView && driftAll.data && <DriftAll devices={driftAll.data.devices} canEdit={canEdit} />}
      {driftView && driftAll.error && <Alert color="down" role="alert">{t('common.error', { message: driftAll.error.message })}</Alert>}
      {data && !driftView && (
        <DataTable
          label={t('inventory.title')}
          rows={devices}
          rowKey={(d) => d.id}
          defaultSort={{ id: 'name' }}
          minWidth={1180}
          {...(canEdit || canRun ? { picked: picks, onPick: setPicks, rowLabel: (d: Device) => d.name } : {})}
          rowStyle={(d) => (d.hidden ? { opacity: 0.6 } : undefined)}
          empty={<Text c="dimmed">{data.devices.length ? t('inventory.noMatch') : t('inventory.empty')}</Text>}
          count={(n) => t('inventory.count', { count: n })}
          columns={[
            { id: 'name', header: t('inventory.field.name'), sort: (d) => d.name, cell: (d) => {
              const look = effectiveLook(d, groups)
              return (
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
              )
            } },
            { id: 'role', header: t('inventory.field.role'), sort: (d) => t(`inventory.role.${d.role}`, { defaultValue: d.role }),
              cell: (d) => t(`inventory.role.${d.role}`, { defaultValue: d.role }) },
            { id: 'group', header: t('inventory.groups.one'), sort: (d) => groupName(d.group_id), cell: (d) => groupName(d.group_id), hideOnPhone: true },
            { id: 'model', header: t('inventory.field.model'), sort: (d) => d.model ?? '', cell: (d) => d.model, hideOnPhone: true },
            { id: 'mgmt_ip', header: t('inventory.field.mgmt_ip'), sort: (d) => d.mgmt_ip ?? '', cell: (d) => d.mgmt_ip, mono: true, hideOnPhone: true },
            { id: 'ports', header: t('inventory.ports'), sort: (d) => (d.ports ? d.ports.up / Math.max(1, d.ports.total) : -1), cell: portsText, mono: true },
            { id: 'uplink', header: t('inventory.uplink.title'), sort: uplinkSort, cell: (d) => <UplinkCell d={d} />, hideOnPhone: true },
            { id: 'last_day', header: t('inventory.lastDay.title'), sort: lastDaySort, descFirst: true, cell: (d) => <LastDayCell d={d} />, hideOnPhone: true },
            { id: 'agent', header: t('inventory.agent'), sort: (d) => agentName(d.agent), cell: (d) => agentName(d.agent), hideOnPhone: true },
            { id: 'drift', header: t('inventoryDrift.badge'), hideOnPhone: true, sort: (d) => d.drift ?? 0, descFirst: true, cell: (d) => !!d.drift && (
              <Badge component={Link} to={devicePath(d.id)} size="sm" variant="light" color="warn" tt="none" style={{ cursor: 'pointer' }}>
                {t('inventoryDrift.count', { count: d.drift })}
              </Badge>
            ) },
            { id: 'source', header: t('inventory.fedBy'), hideOnPhone: true, cell: (d) => (
              <Group gap={4} wrap="nowrap">
                {d.sources.length === 0 && <Badge variant="outline" color="gray" tt="none">{t('inventory.manual')}</Badge>}
                {d.sources.map((src) => <Badge key={src} variant="light" color="gray" tt="none">{sourceName(src)}</Badge>)}
                {d.gone.map((src) => <Badge key={`gone-${src}`} variant="light" color="warn" tt="none">{t('inventory.gone', { source: sourceName(src) })}</Badge>)}
                {d.hidden && <Badge variant="outline" color="gray" tt="none">{t('inventory.hidden')}</Badge>}
              </Group>
            ) },
            { id: 'menu', header: null, width: 44, cell: (d) => (
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
            ) },
          ]}
        />
      )}
      {/* After the table, so it sticks to the bottom of the window while the list scrolls. */}
      {data && !driftView && picked.length > 0 && (
        <PickBar picked={picked} overview={overview} canEdit={canEdit} canRun={canRun} onClear={() => setPicks([])}
          onDone={(text, ok) => setMessage({ ok, text })} />
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
