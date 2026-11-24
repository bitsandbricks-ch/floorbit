import { Badge, Button, Group, Menu, Modal, Paper, SimpleGrid, Stack, Tabs, Text, TextInput, Title } from '@mantine/core'
import { IconCopy, IconDeviceFloppy, IconLayoutDashboard, IconPencil, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useDashboard } from '@/api/queries'
import type { WidgetTile } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { ErrorBanner } from '@/components/ui'
import { pluginName } from '@/lib/pluginName'
import { PluginWidgetCard } from '@/widgets/PluginTiles'
import { add } from '../dashboards/grid'
import { type Board, type Pane, boardName, boardSettings } from '../dashboards/model'
import { TileField } from '../dashboards/PaneForm'
import { PaneView } from '../dashboards/Panes'
import { type SavedWidget, type TilePane, followed, useDeleteWidget, useSaveWidget, useSavedWidgets } from './saved'
import '../dashboards/dashboards.css'
import './widgets.css'
import { CardTable, type CardFilter, ConfirmButton, EmptyState } from '@bitsandbricks/ui'

const AREAS = ['network', 'services', 'traffic', 'power', 'plugins'] as const
type AreaFilter = (typeof AREAS)[number] | 'all'

/** Where Floorbit's own tiles sit in the gallery; the rest are network. */
const CORE_AREAS: Record<string, AreaFilter> = Object.fromEntries([
  ...['service_health', 'lancache', 'agents', 'incidents', 'open_incidents', 'problems'].map((id) => [id, 'services']),
  ...['bandwidth', 'peak', 'traffic', 'traffic_areas', 'traffic_mix', 'flow_services', 'top_ports', 'anomalies',
    'dns_lookups', 'dns_sites', 'dns_blocked', 'launchers'].map((id) => [id, 'traffic']),
  ['power_circuits', 'power'],
])

/** One entry in the gallery: a data tile, with what a pane needs to hold it. */
interface Entry { key: string; area: string; name: string; from?: string; pane: Pane; tile: WidgetTile }

/** The widgets this account may see, with the features that are on. */
function useEntries(): Entry[] {
  const { t } = useTranslation()
  const tiles = useDashboard().data?.tiles ?? []
  return tiles.filter((x): x is WidgetTile => x.kind !== 'action').map((x) => ({
    key: `tile:${x.plugin}/${x.id}`, area: x.plugin === 'floorbit' ? CORE_AREAS[x.id] ?? 'network' : 'plugins', name: x.label,
    from: x.plugin === 'floorbit' ? undefined : pluginName(t, x.plugin, x.plugin_name),
    pane: { kind: 'tile', tile: `${x.plugin}/w/${x.id}` }, tile: x,
  }))
}

/** A widget drawn small and live, as it shows on a dashboard. ``inert``: a preview, not a control. */
function Preview({ entry }: { entry: Entry }) {
  return (
    <div className="fb-widget-preview" inert>
      <PluginWidgetCard tile={entry.tile} />
    </div>
  )
}

/** "Add to dashboard": the widget as a new panel at the end of the dashboard's last section. */
function AddTo({ entry, boards }: { entry: { name: string; pane: Pane }; boards: Board[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [done, setDone] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: (b: Board) => {
      const sections = b.sections.length ? b.sections : [{ panels: [] }]
      const last = sections.length - 1
      const next = sections.map((s, i) => (i === last ? { ...s, panels: add(s.panels, { pane: entry.pane }, 8, 6) } : s))
      return put<Board>(`/api/dashboards/${encodeURIComponent(b.id)}`, {
        name: b.name, sections: next, fit: b.fit, public: !!b.public, ...boardSettings(b),
      })
    },
    onSuccess: (b) => { setDone(b.name); void qc.invalidateQueries({ queryKey: qk.boards }) },
  })
  return (
    <Stack gap={4}>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} loading={save.isPending}
            aria-label={t('widgets.addNamed', { name: entry.name })}>{t('widgets.add')}</Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Label>{t('widgets.addTo')}</Menu.Label>
          {boards.map((b) => <Menu.Item key={b.id} onClick={() => save.mutate(b)}>{boardName(t, b)}</Menu.Item>)}
          {!boards.length && <Menu.Item disabled>{t('widgets.noBoards')}</Menu.Item>}
        </Menu.Dropdown>
      </Menu>
      {done && <Text size="xs" role="status" className="fb-tone-ok">{t('widgets.added', { name: done })}</Text>}
      {save.error && <Text size="xs" role="alert" className="fb-tone-err">{save.error.message}</Text>}
    </Stack>
  )
}

type Tab = 'saved' | 'types'
/** What the editor opens with: a saved widget (``id``), a copy, or a new one from a type. */
type Draft = { id?: string; name: string; pane: TilePane }

/** Widgets (Mike, #1009): the saved ones, each a type with its sources and settings under a name
 *  that any dashboard can show; and the Types, every kind of widget Floorbit can draw. */
export default function Widgets() {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const boards = useQuery({ queryKey: qk.boards, queryFn: () => get<{ layouts: Board[] }>('/api/dashboards'), enabled: canEdit })
  const [tab, setTab] = useState<Tab>(() => (new URLSearchParams(window.location.search).get('tab') === 'types' ? 'types' : 'saved'))
  const [draft, setDraft] = useState<Draft | null>(null)
  const pick = (v: string | null) => {
    const next = v === 'types' ? 'types' : 'saved'
    setTab(next)
    window.history.replaceState(null, '', next === 'types' ? '?tab=types' : window.location.pathname)
  }
  const saved = useSavedWidgets()
  return (
    <Layout title={t('widgets.title')} back={{ href: '/dashboards', label: t('dashboards.title') }}>
      <PageHead title={t('widgets.title')} desc={t('widgets.intro')}
        actions={canEdit && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setDraft({ name: '', pane: { kind: 'tile', tile: '' } })}>
            {t('widgets.new')}
          </Button>
        )} />
      <Tabs value={tab} onChange={pick} mb="md">
        <Tabs.List>
          <Tabs.Tab value="saved" rightSection={saved.data && <Badge size="xs" variant="light">{saved.data.widgets.length}</Badge>}>
            {t('widgets.tabSaved')}
          </Tabs.Tab>
          <Tabs.Tab value="types">{t('widgets.tabTypes')}</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      <ErrorBanner error={boards.error} />
      {tab === 'saved'
        ? <SavedList canEdit={canEdit} boards={boards.data?.layouts ?? []} onEdit={setDraft} />
        : <Types canEdit={canEdit} boards={boards.data?.layouts ?? []} onSave={setDraft} />}
      {draft && <Editor draft={draft} onClose={() => setDraft(null)} onSaved={() => { setDraft(null); pick('saved') }} />}
    </Layout>
  )
}

/** The saved widgets, drawn live as a dashboard shows them, in the shared card table (#1311):
 *  search over the name and the dashboards it is on, a filter for where it is used, pages of 24. */
function SavedList({ canEdit, boards, onEdit }: { canEdit: boolean; boards: Board[]; onEdit: (d: Draft) => void }) {
  const { t } = useTranslation()
  const { data, error, isPending } = useSavedWidgets()
  const remove = useDeleteWidget()
  const used: CardFilter<SavedWidget> = {
    key: 'used', label: t('widgets.usedFilter'), defaultValue: 'all',
    options: (['all', 'used', 'unused'] as const).map((v) => ({ value: v, label: t(`widgets.used.${v}`) })),
    match: (w, v) => (v === 'used') === w.used_on.length > 0,
  }
  return (
    <Stack gap="lg">
      <ErrorBanner error={error ?? remove.error} />
      <CardTable<SavedWidget> items={data?.widgets ?? []} itemKey={(w) => w.id} label={t('widgets.tabSaved')} loading={isPending}
        searchText={(w) => `${w.name} ${w.used_on.join(' ')}`} searchLabel={t('widgets.search')} filters={[used]}
        empty={<EmptyState icon={<IconLayoutDashboard size={24} />} title={t('widgets.noSaved')}
          description={t('widgets.noSavedHint')} />}
        renderCard={(w) => (
          <Paper withBorder radius="lg" className="fb-widget-card" component="article" aria-label={w.name}>
            <SavedPreview widget={w} />
            <Group justify="space-between" wrap="wrap" p="md" gap="sm">
              <div style={{ minWidth: 0 }}>
                <Title order={2} fz="md" lineClamp={2}>{w.name}</Title>
                <Text size="xs" c="dimmed" lineClamp={2}>
                  {w.used_on.length ? t('widgets.usedOn', { names: w.used_on.join(', ') }) : t('widgets.unused')}
                </Text>
              </div>
              {canEdit && (
                <Group gap="xs" wrap="wrap">
                  <Button size="xs" variant="subtle" leftSection={<IconPencil size={14} />} aria-label={t('widgets.editNamed', { name: w.name })}
                    onClick={() => onEdit({ id: w.id, name: w.name, pane: w.pane })}>{t('widgets.edit')}</Button>
                  <Button size="xs" variant="subtle" leftSection={<IconCopy size={14} />} aria-label={t('widgets.copyNamed', { name: w.name })}
                    onClick={() => onEdit({ name: t('widgets.copyName', { name: w.name }), pane: w.pane })}>{t('widgets.copy')}</Button>
                  <ConfirmButton size="xs" variant="subtle" danger label={t('widgets.remove')} aria-label={t('widgets.removeNamed', { name: w.name })}
                    question={t('widgets.removeAsk', { name: w.name })} loading={remove.isPending} onConfirm={() => remove.mutate(w.id)} />
                  <AddTo entry={{ name: w.name, pane: { kind: 'widget', widget: w.id } }} boards={boards} />
                </Group>
              )}
            </Group>
          </Paper>
        )} />
    </Stack>
  )
}

function SavedPreview({ widget }: { widget: Pick<SavedWidget, 'name' | 'pane'> }) {
  return (
    <div className="fb-widget-preview fb-widget-preview-pane" inert>
      {widget.pane.tile ? <PaneView pane={followed(widget, { hide_title: true })} /> : null}
    </div>
  )
}

/** A saved widget's name and settings, with the widget drawn live as it will show. */
function Editor({ draft, onClose, onSaved }: { draft: Draft; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState(draft.name)
  const [pane, setPane] = useState<TilePane>(draft.pane)
  const save = useSaveWidget()
  const title = draft.id ? t('widgets.editTitle') : t('widgets.newTitle')
  return (
    <Modal opened onClose={onClose} title={title} size="xl" centered>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <Stack gap="sm">
          <TextInput label={t('widgets.name')} required maxLength={60} value={name} data-autofocus
            onChange={(e) => setName(e.currentTarget.value)} />
          <TileField pane={pane} onChange={(p) => p.kind === 'tile' && setPane(p)} />
        </Stack>
        <Stack gap="xs" className="fb-widget-editor-side">
          <Text size="sm" fw={500}>{t('widgets.preview')}</Text>
          <div className="fb-widget-editor-preview">
            {pane.tile ? <PaneView pane={followed({ name: name || t('widgets.title'), pane }, {})} />
              : <Text size="sm" c="dimmed">{t('widgets.pickType')}</Text>}
          </div>
          {draft.id && <Text size="xs" c="dimmed">{t('widgets.followHint')}</Text>}
        </Stack>
      </SimpleGrid>
      {save.error && <Text size="sm" role="alert" className="fb-tone-err" mt="sm">{save.error.message}</Text>}
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onClose}>{t('common.cancel')}</Button>
        <Button leftSection={<IconDeviceFloppy size={16} />} loading={save.isPending} disabled={!name.trim() || !pane.tile}
          onClick={() => save.mutate({ id: draft.id, name, pane }, { onSuccess: onSaved })}>{t('widgets.save')}</Button>
      </Group>
    </Modal>
  )
}

/** Every widget type Floorbit can show, live and small, in the shared card table (#1311): search
 *  over the name and the plugin, a filter by area. Add one to a dashboard, or save it as your own. */
function Types({ canEdit, boards, onSave }: { canEdit: boolean; boards: Board[]; onSave: (d: Draft) => void }) {
  const { t } = useTranslation()
  const entries = useEntries()
  const present = AREAS.filter((a) => entries.some((e) => e.area === a))
  const area: CardFilter<Entry> = {
    key: 'area', label: t('widgets.area'), defaultValue: 'all',
    options: (['all', ...present] as AreaFilter[]).map((a) => ({ value: a, label: t(`dashboards.widgetArea.${a}`) })),
    match: (e, v) => e.area === v,
  }
  return (
    <CardTable<Entry> items={entries} itemKey={(e) => e.key} label={t('widgets.tabTypes')}
      searchText={(e) => `${e.name} ${e.from ?? ''}`} searchLabel={t('widgets.search')} filters={[area]}
      renderCard={(e) => (
        <Paper withBorder radius="lg" className="fb-widget-card" component="article" aria-label={e.name}>
          <Preview entry={e} />
          <Group justify="space-between" wrap="wrap" p="md" gap="sm">
            <div style={{ minWidth: 0 }}>
              <Title order={2} fz="md" lineClamp={2}>{e.name}</Title>
              <Text size="xs" c="dimmed">{e.from ?? t(`dashboards.widgetArea.${e.area}`)}</Text>
            </div>
            <Group gap="xs" wrap="nowrap">
              {canEdit && e.pane.kind === 'tile' && (
                <Button size="xs" variant="subtle" leftSection={<IconDeviceFloppy size={14} />} aria-label={t('widgets.saveAsNamed', { name: e.name })}
                  onClick={() => onSave({ name: e.name, pane: e.pane as TilePane })}>{t('widgets.saveAs')}</Button>
              )}
              {canEdit && <AddTo entry={e} boards={boards} />}
            </Group>
          </Group>
        </Paper>
      )} />
  )
}
