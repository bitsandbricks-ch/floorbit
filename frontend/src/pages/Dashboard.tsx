import {
  ActionIcon, Alert, Anchor, Button, Checkbox, Group, Loader, Paper, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, Title,
} from '@mantine/core'
import { IconArrowDown, IconArrowUp, IconLayoutGridAdd, IconMaximize, IconPencil } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { del, get, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useDashboard, useWidget } from '@/api/queries'
import type { ActionResult, ActionTile, DashboardLayout, Tile, WidgetTile } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { WidgetBody } from '@/widgets/WidgetBody'

function TileFrame({ title, from, wide, children }: { title: string; from: string; wide?: boolean; children: React.ReactNode }) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md" style={wide ? { gridColumn: '1 / -1' } : undefined} component="section">
      <Stack gap={10}>
        <div>
          <Title order={3} fz="md">
            {title}
          </Title>
          <Text size="xs" c="dimmed">
            {t('dashboard.from', { plugin: from })}
          </Text>
        </div>
        {children}
      </Stack>
    </Paper>
  )
}

function WidgetCard({ tile }: { tile: WidgetTile }) {
  const { t } = useTranslation()
  const { data, error, isPending } = useWidget(tile)
  return (
    <TileFrame title={tile.label} from={tile.plugin_name} wide={tile.size === 'wide'}>
      {isPending ? (
        <Loader size="sm" aria-label={t('common.loading')} />
      ) : error && !data ? (
        <Text size="sm" className="fb-tone-err" role="alert">
          ✕ {error.message}
        </Text>
      ) : data ? (
        <>
          <WidgetBody widget={data} />
          {data.sub && (
            <Text size="xs" c="dimmed">
              {data.sub}
            </Text>
          )}
          {data.link && (
            <Anchor href={data.link} size="sm">
              {t('common.details')}
            </Anchor>
          )}
        </>
      ) : null}
    </TileFrame>
  )
}

function ActionCard({ tile }: { tile: ActionTile }) {
  const { t } = useTranslation()
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const run = useMutation({
    mutationFn: () => post<ActionResult>(tile.url),
    onSuccess: (r) => setResult({ ok: true, text: r.message }),
    onError: (e) => setResult({ ok: false, text: e.message }),
  })
  return (
    <TileFrame title={tile.label} from={tile.plugin_name}>
      <ConfirmButton label={tile.label} danger={tile.danger} loading={run.isPending} onConfirm={() => run.mutate()} />
      <Text size="sm" role="status" className={result ? (result.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
        {run.isPending ? t('common.working') : result ? `${result.ok ? '✓' : '✕'} ${result.text}` : ''}
      </Text>
    </TileFrame>
  )
}

const keyOf = (tile: Tile) => `${tile.plugin}/${tile.kind === 'action' ? 'a' : 'w'}/${tile.id}`

export function TileGrid({ tiles, columns = 3 }: { tiles: Tile[]; columns?: number }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: Math.min(2, columns), lg: columns }} spacing="md" aria-live="polite">
      {tiles.map((tile) =>
        tile.kind === 'action' ? (
          <ActionCard key={`${tile.plugin}/a/${tile.id}`} tile={tile} />
        ) : (
          <WidgetCard key={`${tile.plugin}/w/${tile.id}`} tile={tile} />
        ),
      )}
    </SimpleGrid>
  )
}

const slug = (name: string) => name.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32) || 'layout'

/** Pick tiles, their order and the columns for a layout, and save it under a name. */
function LayoutEditor({ tiles, layout, onDone }: { tiles: Tile[]; layout: DashboardLayout | null; onDone: (id: string | null) => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState(layout?.name ?? '')
  const [columns, setColumns] = useState(String(layout?.columns ?? 3))
  const known = tiles.map(keyOf)
  const [picked, setPicked] = useState<string[]>(() => layout ? layout.tiles.filter((k) => known.includes(k)) : known)
  const order = [...picked, ...known.filter((k) => !picked.includes(k))]
  const label = (k: string) => {
    const tile = tiles.find((x) => keyOf(x) === k)
    return tile ? `${tile.label} · ${tile.plugin_name}` : k
  }
  const move = (k: string, step: number) => setPicked((p) => {
    const i = p.indexOf(k), j = i + step
    if (i < 0 || j < 0 || j >= p.length) return p
    const out = [...p];[out[i], out[j]] = [out[j], out[i]]
    return out
  })
  const done = (id: string | null) => { void qc.invalidateQueries({ queryKey: qk.dashboardLayouts }); onDone(id) }
  const save = useMutation({
    mutationFn: () => put<DashboardLayout>(`/api/dashboard/layouts/${layout?.id ?? slug(name)}`, { name, tiles: picked, columns: Number(columns) }),
    onSuccess: (saved) => done(saved.id),
  })
  const remove = useMutation({ mutationFn: () => del(`/api/dashboard/layouts/${layout!.id}`), onSuccess: () => done(null) })
  return (
    <Paper withBorder radius="lg" p="md" mb="md" component="section" aria-label={t('dashboard.editLayout')}>
      <Stack gap="sm">
        <Group gap="sm" align="flex-end" wrap="wrap">
          <TextInput label={t('dashboard.layoutName')} placeholder={t('dashboard.layoutPlaceholder')} value={name} maxLength={60}
            onChange={(e) => setName(e.currentTarget.value)} style={{ flex: 1, minWidth: 200 }} />
          <div>
            <Text size="sm" fw={500} mb={4}>{t('dashboard.columns')}</Text>
            <SegmentedControl value={columns} onChange={setColumns} data={['1', '2', '3', '4']} aria-label={t('dashboard.columns')} />
          </div>
        </Group>
        <Text size="sm" c="dimmed">{t('dashboard.pickTiles')}</Text>
        <Stack gap={4}>
          {order.map((k) => (
            <Group key={k} justify="space-between" wrap="nowrap">
              <Checkbox label={label(k)} checked={picked.includes(k)}
                onChange={(e) => { const on = e.currentTarget.checked; setPicked((p) => on ? [...p, k] : p.filter((x) => x !== k)) }} />
              {picked.includes(k) && (
                <Group gap={4} wrap="nowrap">
                  <ActionIcon variant="default" size="sm" aria-label={t('dashboard.up', { tile: label(k) })} onClick={() => move(k, -1)}><IconArrowUp size={14} /></ActionIcon>
                  <ActionIcon variant="default" size="sm" aria-label={t('dashboard.down', { tile: label(k) })} onClick={() => move(k, 1)}><IconArrowDown size={14} /></ActionIcon>
                </Group>
              )}
            </Group>
          ))}
        </Stack>
        {(save.error || remove.error) && <Alert color="down" role="alert">{(save.error || remove.error)!.message}</Alert>}
        <Group gap="xs">
          <Button loading={save.isPending} disabled={!name.trim() || picked.length === 0} onClick={() => save.mutate()}>{t('dashboard.saveLayout')}</Button>
          <Button variant="default" onClick={() => onDone(layout?.id ?? null)}>{t('dashboard.cancel')}</Button>
          {layout && <Button variant="subtle" color="down" loading={remove.isPending} onClick={() => remove.mutate()}>{t('dashboard.deleteLayout')}</Button>}
        </Group>
      </Stack>
    </Paper>
  )
}

/** Plugin tiles (issue #11), with layouts saved per screen (issue #103): ``?layout=<id>``, and
 *  ``&screen=1`` for a kiosk or ops screen without the header. */
export default function Dashboard() {
  const { t } = useTranslation()
  const { data, error, isPending } = useDashboard()
  const [params, setParams] = useSearchParams()
  const canEdit = useCan('floorplan.edit')
  const layouts = useQuery({ queryKey: qk.dashboardLayouts, queryFn: () => get<{ layouts: DashboardLayout[] }>('/api/dashboard/layouts') })
  const [editing, setEditing] = useState<'new' | 'current' | null>(null)
  const screen = params.get('screen') === '1'
  const layout = layouts.data?.layouts.find((l) => l.id === params.get('layout')) ?? null
  const all = data?.tiles ?? []
  const shown = layout ? layout.tiles.map((k) => all.find((x) => keyOf(x) === k)).filter((x): x is Tile => !!x) : all
  const pick = (id: string | null) => {
    setEditing(null)
    const next = new URLSearchParams(params)
    if (id) next.set('layout', id)
    else next.delete('layout')
    setParams(next, { replace: true })
  }
  const body = (
    <>
      {isPending && <Loader aria-label={t('common.loading')} />}
      {error && (
        <Alert color="down" role="alert">
          {t('common.error', { message: error.message })}
        </Alert>
      )}
      {data && all.length === 0 && (
        <Paper withBorder radius="lg" p="lg">
          <Text>{t('dashboard.empty')}</Text>
          <Anchor href="/settings/plugins" mt="sm" display="inline-block">
            {t('dashboard.emptyLink')}
          </Anchor>
        </Paper>
      )}
      {editing && data && <LayoutEditor key={editing} tiles={all} layout={editing === 'current' ? layout : null} onDone={pick} />}
      {data && shown.length > 0 && <TileGrid tiles={shown} columns={layout?.columns ?? 3} />}
      {data && all.length > 0 && layout && shown.length === 0 && <Text c="dimmed">{t('dashboard.layoutEmpty')}</Text>}
    </>
  )
  if (screen) return <main className="fb-dashboard-screen">{body}</main>
  return (
    <Layout title={t('dashboard.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      {all.length > 0 && (
        <Group justify="space-between" mb="md" wrap="wrap" gap="xs">
          <Select aria-label={t('dashboard.layout')} w={240} allowDeselect={false} value={layout?.id ?? ''}
            onChange={(v) => pick(v || null)}
            data={[{ value: '', label: t('dashboard.allTiles') }, ...(layouts.data?.layouts ?? []).map((l) => ({ value: l.id, label: l.name }))]} />
          <Group gap="xs">
            {canEdit && layout && <Button variant="default" leftSection={<IconPencil size={16} />} onClick={() => setEditing('current')}>{t('dashboard.editLayout')}</Button>}
            {canEdit && <Button variant="default" leftSection={<IconLayoutGridAdd size={16} />} onClick={() => setEditing('new')}>{t('dashboard.newLayout')}</Button>}
            <Button variant="default" component="a" href={`/dashboard?${layout ? `layout=${encodeURIComponent(layout.id)}&` : ''}screen=1`}
              leftSection={<IconMaximize size={16} />}>{t('dashboard.screen')}</Button>
          </Group>
        </Group>
      )}
      {body}
    </Layout>
  )
}
