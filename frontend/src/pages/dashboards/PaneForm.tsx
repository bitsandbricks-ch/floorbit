import { Button, Select, SegmentedControl, Stack, Switch, Text, TextInput, Textarea } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { useDashboard, useWidget } from '@/api/queries'
import type { SeatViewData, WidgetTile } from '@/api/types'
import { EntitySelect } from '@/components/EntitySelect'
import { VIEWS } from '@/widgets/views'
import { KIND_PICKS, LEVEL_PINS, type KindPick, type LevelPin } from '@/widgets/level'
import { kindsFor } from '@/widgets/kinds/shape'
import { PRESET_KEYS } from '../plan/layers'
import type { View } from '../plan/model'
import { SeatMap } from '../plan/SeatMap'
import { type Area, MARKS_MODES, type MarksMode, PANE_KINDS, type Pane, type PaneKind, type PlanFilter, TEXT_MAX, TEXT_SIZES, type TextSize, areaView, planPane } from './model'
import { pluginName } from '@/lib/pluginName'

const FILTERS: PlanFilter[] = ['all', 'problems', 'offline', 'recent', 'note', 'checked_in']

/** A fresh pane of ``kind``, keeping the title. */
function blank(kind: PaneKind, title?: string, hide?: boolean): Pane {
  const base = { ...(title ? { title } : {}), ...(hide ? { hide_title: true } : {}) }
  switch (kind) {
    case 'plan': return planPane(base)
    case 'tile': return { kind, tile: '', ...base }
    case 'view': return { kind, view: VIEWS[0]?.id ?? '', ...base }
    case 'text': return { kind, text: '', size: 'l', align: 'start', ...base }
    default: return { kind: 'empty', ...base }
  }
}

/** The settings of the pane picked in the editor. */
export function PaneForm({ pane, onChange }: { pane: Pane; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  return (
    <Stack gap="sm">
      {/* Five kinds don't fit a segmented control in the side panel. */}
      <Select label={t('dashboards.form.kind')} allowDeselect={false} value={pane.kind}
        data={PANE_KINDS.map((k) => ({ value: k, label: t(`dashboards.kind.${k}`) }))}
        onChange={(v) => v && onChange(blank(v as PaneKind, pane.title, pane.hide_title))} />
      <TextInput label={t('dashboards.form.title')} description={t('dashboards.form.titleHint')} maxLength={40} value={pane.title ?? ''}
        onChange={(e) => onChange({ ...pane, title: e.currentTarget.value || undefined })} />
      <Switch label={t('dashboards.form.hideTitle')} checked={!!pane.hide_title}
        onChange={(e) => onChange({ ...pane, hide_title: e.currentTarget.checked || undefined })} />
      {pane.kind === 'text' && <TextFields pane={pane} onChange={onChange} />}
      {pane.kind === 'plan' && <PlanFields pane={pane} onChange={onChange} />}
      {pane.kind === 'view' && (
        <Select label={t('dashboards.form.view')} allowDeselect={false} searchable value={pane.view || null}
          nothingFoundMessage={t('dashboards.form.noViews')}
          data={VIEWS.map((v) => ({ value: v.id, label: t(v.label), group: t(`dashboards.widgetArea.${v.area}`) }))}
          onChange={(v) => v && onChange({ ...pane, view: v })} />
      )}
      {pane.kind === 'view' && (
        <Switch label={t('dashboards.form.expanded')} description={t('dashboards.form.expandedHint')} checked={!!pane.expanded}
          onChange={(e) => onChange({ ...pane, expanded: e.currentTarget.checked || undefined })} />
      )}
      {pane.kind === 'tile' && <TileField pane={pane} onChange={onChange} />}
    </Stack>
  )
}

function TextFields({ pane, onChange }: { pane: Extract<Pane, { kind: 'text' }>; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  return (
    <>
      <Textarea label={t('dashboards.form.text')} description={t('dashboards.form.textHint')} autosize minRows={5} maxRows={14}
        maxLength={TEXT_MAX} value={pane.text} onChange={(e) => onChange({ ...pane, text: e.currentTarget.value })} />
      <div>
        <Text size="sm" fw={500} mb={4}>{t('dashboards.form.size')}</Text>
        <SegmentedControl fullWidth size="xs" value={pane.size} aria-label={t('dashboards.form.size')}
          data={TEXT_SIZES.map((v) => ({ value: v, label: t(`dashboards.textSize.${v}`) }))}
          onChange={(v) => onChange({ ...pane, size: v as TextSize })} />
      </div>
      <div>
        <Text size="sm" fw={500} mb={4}>{t('dashboards.form.align')}</Text>
        <SegmentedControl fullWidth size="xs" value={pane.align} aria-label={t('dashboards.form.align')}
          data={(['start', 'center'] as const).map((v) => ({ value: v, label: t(`dashboards.align.${v}`) }))}
          onChange={(v) => onChange({ ...pane, align: v as 'start' | 'center' })} />
      </div>
    </>
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
        <Select label={t('dashboards.area.block')} allowDeselect={false} searchable placeholder={t('ui.pickBlock')} value={pane.area.id || null}
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
      <div>
        <Text size="sm" fw={500} mb={4}>{t('dashboards.form.marks')}</Text>
        <SegmentedControl fullWidth size="xs" value={pane.marks ?? 'all'} aria-label={t('dashboards.form.marks')}
          data={MARKS_MODES.map((m) => ({ value: m, label: t(`dashboards.marks.${m}`) }))}
          onChange={(v) => onChange({ ...pane, marks: v as MarksMode })} />
        <Text size="xs" c="dimmed" mt={4}>{t('dashboards.form.marksHint')}</Text>
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
  const tile = tiles.find((x) => `${x.plugin}/w/${x.id}` === pane.tile) as WidgetTile | undefined
  return (
    <>
      <Select label={t('dashboards.form.tile')} allowDeselect={false} searchable value={pane.tile || null}
        nothingFoundMessage={t('dashboards.form.noTiles')}
        data={tiles.map((x) => ({ value: `${x.plugin}/w/${x.id}`, label: `${x.label} · ${pluginName(t, x.plugin, x.plugin_name)}` }))}
        onChange={(v) => v && onChange({ kind: 'tile', tile: v, title: pane.title, hide_title: pane.hide_title })} />
      {tile && <WidgetLook pane={pane} tile={tile} onChange={onChange} />}
      <div>
        <Text size="sm" fw={500} mb={4}>{t('dashboards.form.level')}</Text>
        <SegmentedControl fullWidth size="xs" value={pane.level ?? 'auto'} aria-label={t('dashboards.form.level')}
          data={LEVEL_PINS.map((l) => ({ value: l, label: t(`dashboards.level.${l}`) }))}
          onChange={(v) => onChange({ ...pane, level: v === 'auto' ? undefined : (v as LevelPin) })} />
        <Text size="xs" c="dimmed" mt={4}>{t('dashboards.form.levelHint')}</Text>
      </div>
    </>
  )
}

/** How to draw the tile's data: only the kinds its shape allows (a list can't be a graph). */
function WidgetLook({ pane, tile, onChange }: { pane: Extract<Pane, { kind: 'tile' }>; tile: WidgetTile; onChange: (p: Pane) => void }) {
  const { t } = useTranslation()
  const { data } = useWidget(tile)
  const ok = data ? kindsFor(data) : []
  const picks = KIND_PICKS.filter((k) => k === 'auto' || ok.includes(k))
  if (picks.length < 3) return null // only "automatic" and the data's own kind: nothing to choose
  return (
    <Select label={t('dashboards.form.widgetType')} allowDeselect={false} value={pane.type && picks.includes(pane.type) ? pane.type : 'auto'}
      data={picks.map((k) => ({ value: k, label: k === 'auto' ? t('dashboards.widgetType.auto', { kind: t(`dashboards.widgetType.${ok[0]}`) }) : t(`dashboards.widgetType.${k}`) }))}
      onChange={(v) => onChange({ ...pane, type: !v || v === 'auto' ? undefined : (v as KindPick) })} />
  )
}
