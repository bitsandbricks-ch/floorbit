import { Alert, Badge, Button, Group, NumberInput, Paper, SegmentedControl, Select, SimpleGrid, Stack, Switch, Text, TextInput, Title } from '@mantine/core'
import { IconArrowRight, IconCopy, IconDeviceTv, IconLayoutGridAdd, IconPencil, IconPlus, IconRestore, IconSeparator } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { boardHref } from '@/nav/sections'
import { del, get, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { dateTime } from '@/lib/time'
import {
  COLS, MAX_PANELS, MAX_SECTIONS, type Panel, type Section, type Spot, add, paneCount, place, rows, starterSections, total,
} from './dashboards/grid'
import { GridView } from './dashboards/GridView'
import { type Board, type Node, MAX_PANES, TIME_RANGES, type TimeRange, boardName, boardSettings, at, isPane, remove, resize, setPane, slug, split } from './dashboards/model'
import { PaneForm } from './dashboards/PaneForm'
import type { PaneFit } from '@/widgets/levelReport'
import './dashboards/dashboards.css'

/** Dashboards (floorbit/dashboards.py): widgets on a grid, for the ops desk or a big screen.
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
        <Editor key={editId} board={editing} onDone={() => open(null)} onOpen={open} taken={q.data?.layouts.map((b) => b.id) ?? []} />
      </Layout>
    )
  }
  return (
    <Layout title={t('dashboards.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('dashboards.title')} desc={t('dashboards.intro')}
        actions={<Group gap="xs">
          <Button variant="default" component="a" href="/widgets" leftSection={<IconLayoutGridAdd size={16} />}>{t('widgets.title')}</Button>
          {canEdit && <Button leftSection={<IconPlus size={16} />} onClick={() => open('new')}>{t('dashboards.new')}</Button>}
        </Group>} />
      {q.isPending && <LoadingState />}
      <ErrorBanner error={q.error} onRetry={() => void q.refetch()} />
      {q.data && q.data.layouts.length === 0 && (
        <Paper withBorder radius="lg" p="lg"><Text>{t('dashboards.empty')}</Text></Paper>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
        {q.data?.layouts.map((b) => (
          <Paper key={b.id} withBorder radius="lg" p="md" component="section" aria-label={boardName(t, b)}>
            <Stack gap="sm">
              <div className="fb-board-thumb" aria-hidden="true"><Thumbs sections={b.sections} /></div>
              <div>
                <Group gap={6}>
                  <Title order={3} fz="md">{boardName(t, b)}</Title>
                  {(b.builtin || b.changed) && <Badge size="xs" variant="light">{t('dashboards.builtin')}</Badge>}
                  {b.changed && <Badge size="xs" variant="light" color="warn">{t('dashboards.changed')}</Badge>}
                  {b.public && <Badge size="xs" variant="light" color="up">{t('dashboards.publicBadge')}</Badge>}
                </Group>
                <Text size="xs" c="dimmed">
                  {t('dashboards.panes', { count: paneCount(b.sections) })}
                  {b.updated_at ? ` · ${t('dashboards.updated', { when: dateTime(b.updated_at) })}` : ''}
                </Text>
              </div>
              <Group gap="xs">
                {/* Inside the app with the sidebar; the big screen is the second way in. */}
                <Button size="xs" component={Link} to={boardHref(b.id)} rightSection={<IconArrowRight size={14} aria-hidden="true" />}>{t('ui.open')}</Button>
                <Button size="xs" variant="default" component="a" href={`/dashboards/${encodeURIComponent(b.id)}`} leftSection={<IconDeviceTv size={14} />}>{t('board.bigScreen')}</Button>
                {canEdit && <Button size="xs" variant="default" leftSection={<IconPencil size={14} />} onClick={() => open(b.id)}>{t('dashboards.editOne')}</Button>}
              </Group>
            </Stack>
          </Paper>
        ))}
      </SimpleGrid>
    </Layout>
  )
}

/** The grid as boxes, for the list. */
function Thumbs({ sections }: { sections: Section[] }) {
  return (
    <div className="fb-thumb-grid">
      {sections.map((s, i) => (
        <div key={i} className="fb-thumb-section" style={{ flex: `${Math.max(1, rows(s.panels))} 1 0`, gridTemplateRows: `repeat(${Math.max(1, rows(s.panels))}, 1fr)` }}>
          {s.panels.map((p, j) => (
            <div key={j} style={{ gridColumn: `${p.x + 1} / span ${p.w}`, gridRow: `${p.y + 1} / span ${p.h}`, display: 'flex' }}><Thumb node={p.node} /></div>
          ))}
        </div>
      ))}
    </div>
  )
}

function Thumb({ node }: { node: Node }) {
  if (isPane(node)) return <div className={`fb-thumb-pane k-${node.pane.kind}`} />
  return (
    <div className={`fb-split fb-split-${node.split}`}>
      {node.children.map((c, i) => <div key={i} className="fb-split-part" style={{ flexBasis: `${node.sizes[i]}%` }}><Thumb node={c} /></div>)}
    </div>
  )
}

function Editor({ board, onDone, onOpen, taken }: { board: Board | null; onDone: () => void; onOpen: (id: string) => void; taken: string[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState(board?.name ?? '')
  const [sections, setSections] = useState<Section[]>(() => board?.sections ?? starterSections())
  // New dashboards start as a Page (scrolls); a wall picks Screen (#923).
  const [fit, setFit] = useState(board?.fit ?? false)
  const [cycle, setCycle] = useState<number | ''>(board?.cycle ?? '')
  const [range, setRange] = useState<TimeRange | undefined>(board?.range)
  const [open, setOpen] = useState(board?.public ?? false)
  const [frame, setFrame] = useState(board?.frame !== false)
  const [sound, setSound] = useState(!!board?.sound)
  const [selected, setSelected] = useState<Spot | null>({ section: 0, panel: 0, path: [] })
  // How the picked pane draws now, from the pane itself (#928).
  const [drawn, setDrawn] = useState<PaneFit | null>(null)
  const node = selected ? sections[selected.section]?.panels[selected.panel]?.node : undefined
  const picked = node && selected ? at(node, selected.path) : null
  const done = () => { void qc.invalidateQueries({ queryKey: qk.boards }); onDone() }
  const id = board?.id ?? slug(name)
  const save = useMutation({
    mutationFn: () => put<Board>(`/api/dashboards/${id}`, { name, sections, fit, public: open,
      ...boardSettings({ cycle: cycle || undefined, range, frame: frame ? undefined : false, sound: sound || undefined }) }),
    onSuccess: done,
  })
  const drop = useMutation({ mutationFn: () => del(`/api/dashboards/${board!.id}`), onSuccess: done })
  // Reset loses the changes for good: the first click asks.
  const [resetting, setResetting] = useState(false)
  // A copy of the dashboard as saved, as a dashboard of one's own (#923): not public until someone says so.
  const copy = useMutation({
    mutationFn: () => {
      const copyName = t('dashboards.copyName', { name: boardName(t, board!) }).slice(0, 60)
      const base = slug(copyName).slice(0, 29)
      const free = [base, ...Array.from({ length: 98 }, (_, i) => `${base}-${i + 2}`)].find((x) => !taken.includes(x)) ?? `${base}-${Date.now() % 1000}`
      return put<Board>(`/api/dashboards/${free}`, {
        name: copyName, sections: board!.sections, fit: !!board!.fit, public: false,
        ...boardSettings(board!),
      })
    },
    onSuccess: (made) => { void qc.invalidateQueries({ queryKey: qk.boards }); onOpen(made.id) },
  })

  const panels = (s: number, fn: (ps: Panel[]) => Panel[]) =>
    setSections((all) => all.map((sec, i) => (i === s ? { ...sec, panels: fn(sec.panels) } : sec)))
  const withNode = (spot: Spot, fn: (n: Node) => Node) =>
    panels(spot.section, (ps) => ps.map((p, i) => (i === spot.panel ? { ...p, node: fn(p.node) } : p)))
  const full = paneCount(sections) >= MAX_PANES
  const target = selected?.section ?? sections.length - 1
  const addWidget = () => {
    if (total(sections) >= MAX_PANELS || full) return
    const ps = add(sections[target].panels, { pane: { kind: 'empty' } })
    panels(target, () => ps)
    setSelected({ section: target, panel: ps.length - 1, path: [] })
  }
  const addSection = () => {
    if (sections.length >= MAX_SECTIONS) return
    setSections([...sections, { title: t('dashboards.section.new'), panels: [] }])
    setSelected(null)
  }
  return (
    <div className="fb-board-editor">
      <Group className="fb-board-bar" gap="sm" align="flex-end" wrap="wrap">
        <TextInput label={t('dashboards.name')} placeholder={t('dashboards.namePlaceholder')} value={name} maxLength={60}
          onChange={(e) => setName(e.currentTarget.value)} style={{ flex: 1, minWidth: 200 }} />
        <NumberInput label={t('dashboards.cycle')} description={t('dashboards.cycleHint')} w={200} min={10} max={600} value={cycle}
          onChange={(v) => setCycle(typeof v === 'number' ? v : '')} allowDecimal={false} />
        <Select label={t('dashboards.boardRange')} description={t('dashboards.boardRangeHint')} w={220} allowDeselect={false}
          value={range ?? 'auto'} data={['auto', ...TIME_RANGES].map((r) => ({ value: r, label: t(`dashboards.range.${r}`) }))}
          onChange={(v) => setRange(!v || v === 'auto' ? undefined : (v as TimeRange))} />
        <Group gap="xs">
          <Button loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>{t('dashboards.save')}</Button>
          <Button variant="default" onClick={() => onDone()}>{t('dashboards.cancel')}</Button>
          {board && <Button variant="default" component="a" href={`/dashboards/${encodeURIComponent(board.id)}`} leftSection={<IconDeviceTv size={16} />}>{t('dashboards.open')}</Button>}
          {board && <Button variant="default" loading={copy.isPending} leftSection={<IconCopy size={16} />} onClick={() => copy.mutate()}>{t('dashboards.copy')}</Button>}
          {board?.changed && (
            <Button variant="subtle" color="down" loading={drop.isPending} leftSection={<IconRestore size={16} />}
              onClick={() => (resetting ? drop.mutate() : setResetting(true))}>
              {resetting ? t('dashboards.resetConfirm') : t('dashboards.reset')}
            </Button>
          )}
          {board && !board.builtin && !board.changed && <Button variant="subtle" color="down" loading={drop.isPending} onClick={() => drop.mutate()}>{t('dashboards.delete')}</Button>}
        </Group>
      </Group>
      {(save.error || drop.error || copy.error) && <Alert color="down" role="alert" mb="sm">{(save.error || drop.error || copy.error)!.message}</Alert>}
      <Group gap="sm" wrap="wrap">
        <Button size="xs" variant="default" leftSection={<IconLayoutGridAdd size={16} />} onClick={addWidget}
          disabled={total(sections) >= MAX_PANELS || full}>{t('dashboards.edit.addWidget')}</Button>
        <Button size="xs" variant="default" leftSection={<IconSeparator size={16} />} onClick={addSection}
          disabled={sections.length >= MAX_SECTIONS}>{t('dashboards.edit.addSection')}</Button>
        <SegmentedControl size="xs" aria-label={t('dashboards.layout')} value={fit ? 'screen' : 'page'} onChange={(v) => setFit(v === 'screen')}
          data={[{ value: 'page', label: t('dashboards.layoutPage') }, { value: 'screen', label: t('dashboards.layoutScreen') }]} />
        <Switch size="sm" label={t('dashboards.frame')} checked={frame} onChange={(e) => setFrame(e.currentTarget.checked)} />
        <Switch size="sm" label={t('dashboards.sound')} description={t('dashboards.soundHint')} checked={sound}
          onChange={(e) => setSound(e.currentTarget.checked)} style={{ maxWidth: 300 }} />
        <Switch size="sm" label={t('dashboards.public')} description={t('dashboards.publicHint')} checked={open}
          onChange={(e) => setOpen(e.currentTarget.checked)} style={{ maxWidth: 360 }} />
        <Text size="xs" c="dimmed" style={{ flex: 1, minWidth: 200 }}>{t('dashboards.canvasHint', { max: MAX_PANELS, cols: COLS })}</Text>
      </Group>
      <div className="fb-board-work">
        <div className="fb-board-canvas">
          <div className={`fb-board-screen${fit ? '' : ' scroll'}`}>
            <GridView sections={sections} fit={fit} cycle={cycle || undefined} editing={{
              selected,
              onSelect: setSelected,
              onFit: setDrawn,
              onSplit: (spot, dir) => { if (!full) withNode(spot, (n) => split(n, spot.path, dir)); setSelected(spot) },
              onRemove: (spot) => {
                if (spot.path.length) withNode(spot, (n) => remove(n, spot.path))
                else panels(spot.section, (ps) => ps.filter((_, i) => i !== spot.panel))
                setSelected(null)
              },
              onResizeSplit: (spot, border, pct) => withNode(spot, (n) => resize(n, spot.path, border, pct)),
              onPlace: (s, i, box, base) => panels(s, () => place(base, i, box)),
              onSection: (s, change) => {
                if (change === null) {
                  setSections((all) => all.filter((_, i) => i !== s))
                  setSelected(null)
                } else setSections((all) => all.map((sec, i) => (i === s ? { ...sec, ...change } : sec)))
              },
              onMoveSection: (s, by) => {
                setSections((all) => {
                  const next = [...all]
                  const [one] = next.splice(s, 1)
                  next.splice(s + by, 0, one)
                  return next
                })
                setSelected(null)
              },
            }} />
          </div>
        </div>
        <Paper withBorder radius="lg" p="md" className="fb-board-side" component="aside" aria-label={t('dashboards.form.label')}>
          {picked && isPane(picked) && selected
            ? <PaneForm key={`${selected.section}.${selected.panel}.${selected.path.join('.')}`} pane={picked.pane} drawn={drawn}
                onChange={(pane) => withNode(selected, (n) => setPane(n, selected.path, pane))} />
            : <Text size="sm" c="dimmed">{t('dashboards.form.pickOne')}</Text>}
        </Paper>
      </div>
    </div>
  )
}
