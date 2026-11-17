import { Alert, Anchor, Button, Group, NumberInput, Paper, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconDeviceTv, IconPencil, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { del, get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { dateTime } from '@/lib/time'
import {
  type Board, type Node, type Path, MAX_PANES, at, isPane, panes, remove, resize, setPane, slug, split, starter,
} from './dashboards/model'
import { PaneForm } from './dashboards/PaneForm'
import { SplitView } from './dashboards/SplitView'
import './dashboards/dashboards.css'

/** Dashboards (floorbit/dashboards.py): screens split into panes, for the ops desk or a big screen.
 *  ``?edit=<id>`` (or ``?edit=new``) opens the editor. */
export default function Dashboards() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const canEdit = useCan('floorplan.edit')
  const q = useQuery({ queryKey: qk.boards, queryFn: () => get<{ layouts: Board[] }>('/api/dashboards') })
  const editId = canEdit ? params.get('edit') : null
  const editing = editId === 'new' ? null : q.data?.layouts.find((b) => b.id === editId) ?? null
  const open = (id: string | null) => {
    const next = new URLSearchParams(params)
    if (id) next.set('edit', id)
    else next.delete('edit')
    setParams(next)
  }
  if (editId && (editId === 'new' || editing)) {
    return (
      <Layout title={t('dashboards.title')} back={{ href: '/dashboards', label: t('dashboards.title') }} full>
        <Editor key={editId} board={editing} onDone={() => open(null)} />
      </Layout>
    )
  }
  return (
    <Layout title={t('dashboards.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('dashboards.title')} desc={t('dashboards.intro')}
        actions={canEdit && <Button leftSection={<IconPlus size={16} />} onClick={() => open('new')}>{t('dashboards.new')}</Button>} />
      {q.isPending && <LoadingState />}
      <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />
      {q.data && q.data.layouts.length === 0 && (
        <Paper withBorder radius="lg" p="lg"><Text>{t('dashboards.empty')}</Text></Paper>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
        {q.data?.layouts.map((b) => (
          <Paper key={b.id} withBorder radius="lg" p="md" component="section" aria-label={b.name}>
            <Stack gap="sm">
              <div className="fb-board-thumb" aria-hidden="true"><Thumb node={b.root} /></div>
              <div>
                <Title order={3} fz="md">{b.name}</Title>
                <Text size="xs" c="dimmed">
                  {t('dashboards.panes', { count: panes(b.root) })}
                  {b.updated_at ? ` · ${t('dashboards.updated', { when: dateTime(b.updated_at) })}` : ''}
                </Text>
              </div>
              <Group gap="xs">
                <Button size="xs" component="a" href={`/dashboards/${encodeURIComponent(b.id)}`} leftSection={<IconDeviceTv size={14} />}>{t('dashboards.open')}</Button>
                {canEdit && <Button size="xs" variant="default" leftSection={<IconPencil size={14} />} onClick={() => open(b.id)}>{t('dashboards.editOne')}</Button>}
              </Group>
            </Stack>
          </Paper>
        ))}
      </SimpleGrid>
      <Text size="sm" c="dimmed" mt="md">
        {t('dashboards.tiles')} <Anchor href="/dashboard">{t('dashboards.tilesLink')}</Anchor>
      </Text>
    </Layout>
  )
}

/** The split as boxes, for the list. */
function Thumb({ node }: { node: Node }) {
  if (isPane(node)) return <div className={`fb-thumb-pane k-${node.pane.kind}`} />
  return (
    <div className={`fb-split fb-split-${node.split}`}>
      {node.children.map((c, i) => <div key={i} className="fb-split-part" style={{ flexBasis: `${node.sizes[i]}%` }}><Thumb node={c} /></div>)}
    </div>
  )
}

function Editor({ board, onDone }: { board: Board | null; onDone: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState(board?.name ?? '')
  const [root, setRoot] = useState<Node>(() => board?.root ?? starter())
  const [cycle, setCycle] = useState<number | ''>(board?.cycle ?? '')
  const [selected, setSelected] = useState<Path | null>([0])
  const picked = selected ? at(root, selected) : null
  const done = () => { void qc.invalidateQueries({ queryKey: qk.boards }); onDone() }
  const id = board?.id ?? slug(name)
  const save = useMutation({
    mutationFn: () => put<Board>(`/api/dashboards/${id}`, { name, root, ...(cycle ? { cycle } : {}) }),
    onSuccess: done,
  })
  const drop = useMutation({ mutationFn: () => del(`/api/dashboards/${board!.id}`), onSuccess: done })
  return (
    <div className="fb-board-editor">
      <Group className="fb-board-bar" gap="sm" align="flex-end" wrap="wrap">
        <TextInput label={t('dashboards.name')} placeholder={t('dashboards.namePlaceholder')} value={name} maxLength={60}
          onChange={(e) => setName(e.currentTarget.value)} style={{ flex: 1, minWidth: 200 }} />
        <NumberInput label={t('dashboards.cycle')} description={t('dashboards.cycleHint')} w={200} min={10} max={600} value={cycle}
          onChange={(v) => setCycle(typeof v === 'number' ? v : '')} allowDecimal={false} />
        <Group gap="xs">
          <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>{t('dashboards.save')}</Button>
          <Button variant="default" onClick={() => onDone()}>{t('dashboards.cancel')}</Button>
          {board && <Button variant="default" component="a" href={`/dashboards/${encodeURIComponent(board.id)}`} leftSection={<IconDeviceTv size={16} />}>{t('dashboards.open')}</Button>}
          {board && <Button variant="subtle" color="down" loading={drop.isPending} onClick={() => drop.mutate()}>{t('dashboards.delete')}</Button>}
        </Group>
      </Group>
      {(save.error || drop.error) && <Alert color="down" role="alert" mb="sm">{(save.error || drop.error)!.message}</Alert>}
      <div className="fb-board-work">
        <div className="fb-board-canvas">
          <Text size="xs" c="dimmed" mb={4}>{t('dashboards.canvasHint', { max: MAX_PANES })}</Text>
          <div className="fb-board-screen">
            <SplitView node={root} cycle={cycle || undefined} editing={{
              selected,
              onSelect: setSelected,
              onSplit: (p, dir) => { const next = split(root, p, dir); setRoot(next); setSelected(p) },
              onRemove: (p) => { setRoot(remove(root, p)); setSelected(null) },
              onResize: (p, border, pct) => setRoot((r) => resize(r, p, border, pct)),
            }} />
          </div>
        </div>
        <Paper withBorder radius="lg" p="md" className="fb-board-side" component="aside" aria-label={t('dashboards.form.label')}>
          {picked && isPane(picked)
            ? <PaneForm key={selected!.join('.')} pane={picked.pane} onChange={(pane) => setRoot(setPane(root, selected!, pane))} />
            : <Text size="sm" c="dimmed">{t('dashboards.form.pickOne')}</Text>}
        </Paper>
      </div>
    </div>
  )
}
