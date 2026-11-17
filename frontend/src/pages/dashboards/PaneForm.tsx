import { Button, Select, SegmentedControl, Stack, Text, TextInput } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useDashboard } from '@/api/queries'
import type { DashboardLayout, SeatViewData } from '@/api/types'
import { EntitySelect } from '@/components/EntitySelect'
import { VIEWS } from '@/widgets/views'
import { PRESET_KEYS } from '../plan/layers'
import type { View } from '../plan/model'
import { SeatMap } from '../plan/SeatMap'
import { type Area, PAGES, PANE_KINDS, type Pane, type PaneKind, type PlanFilter, areaView, planPane } from './model'

const FILTERS: PlanFilter[] = ['all', 'problems', 'offline', 'recent', 'note', 'checked_in']

/** A fresh pane of ``kind``, keeping the title. */
function blank(kind: PaneKind, title?: string): Pane {
  const base = title ? { title } : {}
  switch (kind) {
    case 'plan': return planPane(base)
    case 'tile': return { kind, tile: '', ...base }
    case 'dashboard': return { kind, layout: '', ...base }
    case 'page': return { kind, page: 'health', ...base }
    case 'view': return { kind, view: VIEWS[0]?.id ?? '', ...base }
    default: return { kind: 'empty', ...base }
  }
}

/** The settings of the pane picked in the editor. */
export function PaneForm({ pane, onChange }: { pane: Pane; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  return (
    <Stack gap="sm">
      <div>
        <Text size="sm" fw={500} mb={4}>{t('dashboards.form.kind')}</Text>
        <SegmentedControl fullWidth size="xs" value={pane.kind} onChange={(v) => onChange(blank(v as PaneKind, pane.title))}
          aria-label={t('dashboards.form.kind')} data={PANE_KINDS.map((k) => ({ value: k, label: t(`dashboards.kind.${k}`) }))} />
      </div>
      <TextInput label={t('dashboards.form.title')} description={t('dashboards.form.titleHint')} maxLength={40} value={pane.title ?? ''}
        onChange={(e) => onChange({ ...pane, title: e.currentTarget.value || undefined })} />
      {pane.kind === 'plan' && <PlanFields pane={pane} onChange={onChange} />}
      {pane.kind === 'view' && (
        <Select label={t('dashboards.form.view')} allowDeselect={false} searchable value={pane.view || null}
          nothingFoundMessage={t('dashboards.form.noViews')}
          data={VIEWS.map((v) => ({ value: v.id, label: t(v.label), group: t(`dashboards.area.${v.area}`, { defaultValue: v.area }) }))}
          onChange={(v) => v && onChange({ ...pane, view: v })} />
      )}
      {pane.kind === 'tile' && <TileField pane={pane} onChange={onChange} />}
      {pane.kind === 'dashboard' && <DashboardField pane={pane} onChange={onChange} />}
      {pane.kind === 'page' && (
        <Select label={t('dashboards.form.page')} allowDeselect={false} value={pane.page}
          data={PAGES.map((p) => ({ value: p, label: t(`dashboards.page.${p}`) }))}
          onChange={(v) => v && onChange({ ...pane, page: v as typeof pane.page })} />
      )}
    </Stack>
  )
}

function PlanFields({ pane, onChange }: { pane: Extract<Pane, { kind: 'plan' }>; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  const q = useQuery({
    queryKey: qk.plan(pane.hall),
    queryFn: () => get<SeatViewData>(`/api/plan${pane.hall ? `?hall=${encodeURIComponent(pane.hall)}` : ''}`),
  })
  const drawing = q.data?.drawing
  const zones = (drawing?.marks ?? []).filter((m) => m.kind === 'zone' && m.id)
  const blocks = (drawing?.shapes ?? []).filter((b) => b.name)
  const setArea = (area: Area) => onChange({ ...pane, area })
  return (
    <>
      <EntitySelect kind="halls" label={t('dashboards.form.hall')} description={t('dashboards.form.hallHint')} clearable
        value={pane.hall || null} onChange={(v) => onChange({ ...pane, hall: v ?? '', area: { kind: 'hall' } })} />
      <div>
        <Text size="sm" fw={500} mb={4}>{t('dashboards.form.area')}</Text>
        <SegmentedControl fullWidth size="xs" value={pane.area.kind} aria-label={t('dashboards.form.area')}
          data={(['hall', 'block', 'zone', 'box'] as const).map((k) => ({ value: k, label: t(`dashboards.area.${k}`) }))}
          onChange={(v) => {
            if (v === 'hall') setArea({ kind: 'hall' })
            else if (v === 'block') setArea({ kind: 'block', id: blocks[0]?.name ?? '' })
            else if (v === 'zone') setArea({ kind: 'zone', id: zones[0]?.id ?? '' })
            else if (drawing) setArea({ kind: 'box', ...(areaView({ kind: 'hall' }, drawing) ?? { x: 0, y: 0, w: 1600, h: 1000 }) })
          }} />
      </div>
      {pane.area.kind === 'block' && (
        <Select label={t('dashboards.area.block')} allowDeselect={false} searchable value={pane.area.id || null}
          data={blocks.map((b) => b.name)} nothingFoundMessage={t('dashboards.form.noBlocks')}
          onChange={(v) => v && setArea({ kind: 'block', id: v })} />
      )}
      {pane.area.kind === 'zone' && (zones.length
        ? <Select label={t('dashboards.area.zone')} allowDeselect={false} value={pane.area.id || null}
            data={zones.map((z) => ({ value: z.id!, label: z.label || t('dashboards.form.unnamedZone') }))}
            onChange={(v) => v && setArea({ kind: 'zone', id: v })} />
        : <Text size="sm" c="dimmed">{t('dashboards.form.noZones')}</Text>)}
      {pane.area.kind === 'box' && q.data && drawing && (
        <BoxPicker data={q.data} box={pane.area} onPick={(v) => setArea({ kind: 'box', ...v })} />
      )}
      <div>
        <Text size="sm" fw={500} mb={4}>{t('dashboards.form.preset')}</Text>
        <SegmentedControl fullWidth size="xs" value={pane.preset} aria-label={t('dashboards.form.preset')}
          data={PRESET_KEYS.map((p) => ({ value: p, label: t(`plan.layers.preset.${p}`) }))}
          onChange={(v) => onChange({ ...pane, preset: v as typeof pane.preset })} />
      </div>
      <Select label={t('dashboards.form.show')} allowDeselect={false} value={pane.show}
        data={FILTERS.map((f) => ({ value: f, label: t(`plan.filter.${f}`) }))}
        onChange={(v) => v && onChange({ ...pane, show: v as PlanFilter })} />
      <div>
        <Text size="sm" fw={500} mb={4}>{t('dashboards.form.labels')}</Text>
        <SegmentedControl fullWidth size="xs" value={pane.labels} aria-label={t('dashboards.form.labels')}
          data={(['auto', 'all', 'none'] as const).map((l) => ({ value: l, label: t(`dashboards.labels.${l}`) }))}
          onChange={(v) => onChange({ ...pane, labels: v as typeof pane.labels })} />
      </div>
    </>
  )
}

/** "The view I zoomed to": a small plan to pan and zoom, and a button that keeps what it shows. */
function BoxPicker({ data, box, onPick }: { data: SeatViewData; box: View; onPick: (v: View) => void }) {
  const { t } = useTranslation()
  const [view, setView] = useState<View>(box)
  const changed = useMemo(() => ['x', 'y', 'w', 'h'].some((k) => Math.abs(view[k as keyof View] - box[k as keyof View]) > 0.5), [view, box])
  return (
    <Stack gap={6}>
      <Text size="sm" c="dimmed">{t('dashboards.form.boxHint')}</Text>
      <div className="fb-box-picker">
        <SeatMap data={data} view={view} setView={setView} filter="all" selected={null} onSelect={() => {}} />
      </div>
      <Button size="xs" variant={changed ? 'filled' : 'default'} disabled={!changed}
        onClick={() => onPick({ x: Math.round(view.x), y: Math.round(view.y), w: Math.max(1, Math.round(view.w)), h: Math.max(1, Math.round(view.h)) })}>
        {t('dashboards.form.useView')}
      </Button>
    </Stack>
  )
}

function TileField({ pane, onChange }: { pane: Extract<Pane, { kind: 'tile' }>; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  const { data } = useDashboard()
  const tiles = (data?.tiles ?? []).filter((x) => x.kind !== 'action')
  return (
    <Select label={t('dashboards.form.tile')} allowDeselect={false} searchable value={pane.tile || null}
      nothingFoundMessage={t('dashboards.form.noTiles')}
      data={tiles.map((x) => ({ value: `${x.plugin}/w/${x.id}`, label: `${x.label} · ${x.plugin_name}` }))}
      onChange={(v) => v && onChange({ ...pane, tile: v })} />
  )
}

function DashboardField({ pane, onChange }: { pane: Extract<Pane, { kind: 'dashboard' }>; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  const layouts = useQuery({ queryKey: qk.dashboardLayouts, queryFn: () => get<{ layouts: DashboardLayout[] }>('/api/dashboard/layouts') })
  return (
    <Select label={t('dashboards.form.dashboard')} allowDeselect={false} value={pane.layout || null}
      nothingFoundMessage={t('dashboards.form.noDashboards')}
      data={(layouts.data?.layouts ?? []).map((l) => ({ value: l.id, label: l.name }))}
      onChange={(v) => v && onChange({ ...pane, layout: v })} />
  )
}
