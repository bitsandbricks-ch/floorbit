import { Alert, Button, Chip, Group, Menu, Modal, Paper, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconArrowsMaximize, IconPlus, IconSearch } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useDashboard, useFeaturesOff, useMe } from '@/api/queries'
import type { WidgetTile } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { pluginName } from '@/lib/pluginName'
import { WidgetCard } from '@/widgets/TileCard'
import { VIEWS, VIEW_COMPONENTS, type ViewDef } from '@/widgets/views'
import { add } from '../dashboards/grid'
import { type Board, type Pane, boardName } from '../dashboards/model'
import '../dashboards/dashboards.css'
import './widgets.css'

const AREAS = ['network', 'services', 'traffic', 'power', 'plugins'] as const
type AreaFilter = (typeof AREAS)[number] | 'all'

/** One entry in the gallery: a rich widget or a plugin's data tile, with what a pane needs to hold it. */
interface Entry { key: string; area: string; name: string; from?: string; pane: Pane; view?: ViewDef; tile?: WidgetTile }

/** The widgets this account may see, with the features that are on. */
function useEntries(): Entry[] {
  const { t } = useTranslation()
  const off = useFeaturesOff()
  const me = useMe().data
  const tiles = useDashboard().data?.tiles ?? []
  const allowed = (p?: string) => !p || !me?.enabled || !!me.user?.permissions?.includes(p as never)
  const views: Entry[] = VIEWS.filter((v) => (!v.feature || !off.includes(v.feature)) && allowed(v.permission))
    .map((v) => ({ key: `view:${v.id}`, area: v.area, name: t(v.label), pane: { kind: 'view', view: v.id }, view: v }))
  const plugin: Entry[] = tiles.filter((x): x is WidgetTile => x.kind !== 'action').map((x) => ({
    key: `tile:${x.plugin}/${x.id}`, area: x.plugin === 'floorbit' ? 'network' : 'plugins', name: x.label,
    from: x.plugin === 'floorbit' ? undefined : pluginName(t, x.plugin, x.plugin_name),
    pane: { kind: 'tile', tile: `${x.plugin}/w/${x.id}` }, tile: x,
  }))
  return [...views, ...plugin]
}

/** A widget drawn small and live, as it shows on a dashboard. ``inert``: a preview, not a control. */
function Preview({ entry }: { entry: Entry }) {
  const View = entry.view ? VIEW_COMPONENTS[entry.view.id] : null
  return (
    <div className="fb-widget-preview" inert>
      {View ? <Suspense fallback={<LoadingState lines />}><View expanded={false} /></Suspense>
        : entry.tile ? <WidgetCard tile={entry.tile} /> : null}
    </div>
  )
}

/** "Add to dashboard": the widget as a new panel at the end of the dashboard's last section. */
function AddTo({ entry, boards }: { entry: Entry; boards: Board[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [done, setDone] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: (b: Board) => {
      const sections = b.sections.length ? b.sections : [{ panels: [] }]
      const last = sections.length - 1
      const next = sections.map((s, i) => (i === last ? { ...s, panels: add(s.panels, { pane: entry.pane }, 8, 6) } : s))
      return put<Board>(`/api/dashboards/${encodeURIComponent(b.id)}`, {
        name: b.name, sections: next, fit: b.fit, public: !!b.public, ...(b.cycle ? { cycle: b.cycle } : {}),
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

/** Every widget Floorbit can show, live and small, by area: pick one for a dashboard or open it big. */
export default function Widgets() {
  const { t } = useTranslation()
  const canEdit = useCan('floorplan.edit')
  const entries = useEntries()
  const boards = useQuery({ queryKey: qk.boards, queryFn: () => get<{ layouts: Board[] }>('/api/dashboards'), enabled: canEdit })
  const [area, setArea] = useState<AreaFilter>('all')
  const [search, setSearch] = useState('')
  const [big, setBig] = useState<Entry | null>(null)
  const needle = search.trim().toLowerCase()
  const shown = entries.filter((e) => (area === 'all' || e.area === area) && (!needle || e.name.toLowerCase().includes(needle)))
  const count = (a: AreaFilter) => entries.filter((e) => a === 'all' || e.area === a).length
  const BigView = big?.view ? VIEW_COMPONENTS[big.view.id] : null
  return (
    <Layout title={t('widgets.title')} back={{ href: '/dashboards', label: t('dashboards.title') }}>
      <PageHead title={t('widgets.title')} desc={t('widgets.intro')}
        actions={<TextInput aria-label={t('widgets.search')} placeholder={t('widgets.search')} value={search} w={260}
          leftSection={<IconSearch size={16} aria-hidden="true" />} onChange={(e) => setSearch(e.currentTarget.value)} />} />
      <Stack gap="lg">
        <Chip.Group value={area} onChange={(v) => setArea(v as AreaFilter)}>
          <Group gap="xs" role="group" aria-label={t('widgets.area')}>
            {(['all', ...AREAS] as AreaFilter[]).filter((a) => a === 'all' || count(a)).map((a) => (
              <Chip key={a} value={a} variant="outline">{t(`dashboards.widgetArea.${a}`)} {count(a)}</Chip>
            ))}
          </Group>
        </Chip.Group>
        <ErrorBanner error={boards.error} />
        {!shown.length && <Alert color="gray" variant="light">{t('widgets.none')}</Alert>}
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="lg">
          {shown.map((e) => (
            <Paper key={e.key} withBorder radius="lg" className="fb-widget-card" component="article" aria-label={e.name}>
              <Preview entry={e} />
              <Group justify="space-between" wrap="wrap" p="md" gap="sm">
                <div style={{ minWidth: 0 }}>
                  <Title order={2} fz="md" lineClamp={2}>{e.name}</Title>
                  <Text size="xs" c="dimmed">{e.from ?? t(`dashboards.widgetArea.${e.area}`)}</Text>
                </div>
                <Group gap="xs" wrap="nowrap">
                  {e.view && (
                    <Button size="xs" variant="subtle" leftSection={<IconArrowsMaximize size={14} />} onClick={() => setBig(e)}
                      aria-label={t('dashboards.pane.openBigNamed', { name: e.name })}>{t('widgets.open')}</Button>
                  )}
                  {canEdit && <AddTo entry={e} boards={boards.data?.layouts ?? []} />}
                </Group>
              </Group>
            </Paper>
          ))}
        </SimpleGrid>
      </Stack>
      {big && BigView && (
        <BigModal title={big.name} onClose={() => setBig(null)}>
          <Suspense fallback={<LoadingState />}><BigView expanded /></Suspense>
        </BigModal>
      )}
    </Layout>
  )
}

function BigModal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <Modal opened onClose={onClose} title={title} size="90%" centered classNames={{ body: 'fb-view-big' }}>{children}</Modal>
  )
}
