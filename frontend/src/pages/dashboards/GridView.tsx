import { ActionIcon, Group, Text, TextInput, Tooltip, UnstyledButton } from '@mantine/core'
import { IconArrowDown, IconArrowUp, IconChevronDown, IconChevronRight, IconGripVertical, IconTrash } from '@tabler/icons-react'
import { useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { COLS, type Panel, ROW_PX, type Section, type Spot, phonePair, rows, snapHeight, stepHeight } from './grid'
import type { Path, Split } from './model'
import { SplitView } from './SplitView'
import { Drill, type PaneFit } from '@bitsandbricks/widgets'
import { LargeContext, PaneKey, paneAt, paneKey, useLarge } from './large'
import { LargeBar } from './LargeBar'
import { DeviceGlance } from './DeviceGlance'
import { useScreen } from './screen'
import { PaneView } from './Panes'

export interface GridEditing {
  selected: Spot | null
  onSelect: (spot: Spot) => void
  onSplit: (spot: Spot, dir: Split) => void
  onRemove: (spot: Spot) => void
  onResizeSplit: (spot: Spot, border: number, pct: number) => void
  /** Panel ``panel`` of ``section`` moved or resized to ``box``, starting from ``base`` (the panels as
   *  they were when the drag began, so the others' room-making doesn't pile up). */
  onPlace: (section: number, panel: number, box: Partial<Panel>, base: Panel[]) => void
  onSection: (section: number, change: Partial<Section> | null) => void
  onMoveSection: (section: number, by: -1 | 1) => void
  onFit?: (fit: PaneFit | null) => void
}

const GAP = 8

/** A dashboard's sections and their panels on the grid. With ``fit`` the rows share the screen's
 *  height (each section by its rows); otherwise rows are ROW_PX high and the page scrolls. */
export function GridView({ sections, fit, cycle, editing, backAfter }: {
  sections: Section[]; fit: boolean; cycle?: number; editing?: GridEditing
  /** Seconds after which a large pane goes back to the dashboard by itself (a wall). */
  backAfter?: number
}) {
  const [folded, setFolded] = useState<Record<number, boolean>>({})
  const { open, close } = useLarge()
  // "Make large" (#925): the one pane fills the dashboard's area; a key that no longer fits shows the dashboard.
  const large = !editing && open ? paneAt(sections, open) : null
  // The device of the row picked in the large widget; a public wall has no account to read it with.
  const [glance, setGlance] = useState<string | null>(null)
  const { publicId } = useScreen()
  const closeGlance = useCallback(() => setGlance(null), [])
  if (large) {
    return (
      <div className={`fb-grid fb-grid-large${fit ? ' fit' : ''}`}>
        <LargeBar onBack={() => { setGlance(null); close() }} backAfter={glance ? undefined : backAfter} />
        <div className={`fb-grid-large-body${glance ? ' glancing' : ''}`}>
          <Drill.Provider value={publicId ? null : setGlance}>
            <LargeContext.Provider value><PaneView pane={large} cycle={cycle} /></LargeContext.Provider>
          </Drill.Provider>
          {glance && <DeviceGlance key={glance} id={glance} onClose={closeGlance} />}
        </div>
      </div>
    )
  }
  return (
    <div className={`fb-grid${fit ? ' fit' : ''}${editing ? ' editing' : ''}`}>
      {sections.map((section, s) => {
        // On a screen, folding is only for whoever looks at it; in the editor it's saved.
        const closed = editing ? !!section.folded : folded[s] ?? !!section.folded
        const toggle = () => (editing ? editing.onSection(s, { folded: !section.folded || undefined }) : setFolded({ ...folded, [s]: !closed }))
        const n = Math.max(1, rows(section.panels))
        return (
          <section key={s} className="fb-grid-section" aria-label={section.title || undefined}
            style={fit && !closed ? { flex: `${n} 1 0` } : undefined}>
            {(s > 0 || section.title || editing) && (
              <SectionHead section={section} index={s} count={sections.length} closed={closed} onToggle={toggle} editing={editing} />
            )}
            {!closed && (
              <GridBody section={section} index={s} fit={fit} rows={n} cycle={cycle} editing={editing} />
            )}
          </section>
        )
      })}
    </div>
  )
}

function SectionHead({ section, index, count, closed, onToggle, editing }: {
  section: Section; index: number; count: number; closed: boolean; onToggle: () => void; editing?: GridEditing
}) {
  const { t } = useTranslation()
  const Chevron = closed ? IconChevronRight : IconChevronDown
  return (
    <div className={`fb-grid-head${section.title || editing ? '' : ' line'}`}>
      {(section.title || editing) && (
        <UnstyledButton className="fb-grid-fold" onClick={onToggle} aria-expanded={!closed}
          aria-label={closed ? t('dashboards.section.open') : t('dashboards.section.fold')}>
          <Chevron size={18} />
        </UnstyledButton>
      )}
      {editing ? (
        <TextInput size="xs" variant="unstyled" className="fb-grid-title-input" maxLength={60} value={section.title ?? ''}
          placeholder={t('dashboards.section.untitled')} aria-label={t('dashboards.section.title')}
          onChange={(e) => editing.onSection(index, { title: e.currentTarget.value || undefined })} />
      ) : section.title && <Text fw={800} className="fb-grid-title">{section.title}</Text>}
      <span className="fb-grid-rule" />
      {editing && (
        <Group gap={4} wrap="nowrap">
          <Tooltip label={t('dashboards.section.up')}><ActionIcon size="sm" variant="subtle" disabled={index === 0} aria-label={t('dashboards.section.up')} onClick={() => editing.onMoveSection(index, -1)}><IconArrowUp size={14} /></ActionIcon></Tooltip>
          <Tooltip label={t('dashboards.section.down')}><ActionIcon size="sm" variant="subtle" disabled={index === count - 1} aria-label={t('dashboards.section.down')} onClick={() => editing.onMoveSection(index, 1)}><IconArrowDown size={14} /></ActionIcon></Tooltip>
          <Tooltip label={t('dashboards.section.remove')}><ActionIcon size="sm" variant="subtle" color="down" disabled={count === 1} aria-label={t('dashboards.section.remove')} onClick={() => editing.onSection(index, null)}><IconTrash size={14} /></ActionIcon></Tooltip>
        </Group>
      )}
    </div>
  )
}

function GridBody({ section, index, fit, rows: n, cycle, editing }: {
  section: Section; index: number; fit: boolean; rows: number; cycle?: number; editing?: GridEditing
}) {
  const { t } = useTranslation()
  const body = useRef<HTMLDivElement>(null)
  // The panel being resized: its size in cells shows on it while the corner moves (#928).
  const [sizing, setSizing] = useState<number | null>(null)
  // Drags in grid cells: pointer travel over one cell's width (or one row's height) moves a cell.
  const drag = (i: number, mode: 'move' | 'size') => (e: React.PointerEvent<HTMLElement>) => {
    if (!editing || !body.current) return
    e.preventDefault()
    e.stopPropagation()
    const el = e.currentTarget
    el.setPointerCapture(e.pointerId)
    const rect = body.current.getBoundingClientRect()
    const col = (rect.width + GAP) / COLS
    const row = fit ? (rect.height + GAP) / n : ROW_PX + GAP
    const base = section.panels
    const start = base[i]
    const x0 = e.clientX, y0 = e.clientY
    const move = (ev: PointerEvent) => {
      const dx = Math.round((ev.clientX - x0) / col), dy = Math.round((ev.clientY - y0) / row)
      // A Page snaps the height to small, medium or large (#923); a Screen shares its height out.
      const h = fit ? start.h + dy : snapHeight(start.h + dy)
      editing.onPlace(index, i, mode === 'move' ? { x: start.x + dx, y: start.y + dy } : { w: start.w + dx, h }, base)
    }
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); setSizing(null) }
    if (mode === 'size') setSizing(i)
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
  }
  // Keyboard: arrows move the panel a cell, with Shift they resize it.
  const keys = (i: number) => (e: React.KeyboardEvent) => {
    if (!editing) return
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key]
    if (!d) return
    e.preventDefault()
    const p = section.panels[i]
    const h = !d[1] || fit ? p.h + d[1] : stepHeight(p.h, d[1] as 1 | -1)
    editing.onPlace(index, i, e.shiftKey ? { w: p.w + d[0], h } : { x: p.x + d[0], y: p.y + d[1] }, section.panels)
  }
  const template = fit ? `repeat(${n}, minmax(0, 1fr))` : `repeat(${n}, ${ROW_PX}px)`
  return (
    <div ref={body} className="fb-grid-body" style={{ gridTemplateRows: template, gap: GAP }}>
      {section.panels.map((p, i) => {
        const here = (path: Path): Spot => ({ section: index, panel: i, path })
        const sel = editing?.selected
        return (
          <div key={i} className={`fb-grid-item${phonePair(p) ? ' pair' : ''}`}
            style={{ gridColumn: `${p.x + 1} / span ${p.w}`, gridRow: `${p.y + 1} / span ${p.h}`, ['--rows' as string]: p.h, ['--at' as string]: p.y * COLS + p.x }}>
            <PaneKey.Provider value={editing ? null : paneKey(index, i)}>
              <SplitView node={p.node} cycle={cycle} editing={editing && {
                selected: sel && sel.section === index && sel.panel === i ? sel.path : null,
                onSelect: (path) => editing.onSelect(here(path)),
                onSplit: (path, dir) => editing.onSplit(here(path), dir),
                onRemove: (path) => editing.onRemove(here(path)),
                onResize: (path, border, pct) => editing.onResizeSplit(here(path), border, pct),
                onFit: editing.onFit,
              }} />
            </PaneKey.Provider>
            {editing && (
              <>
                <button type="button" className="fb-grid-grip" aria-label={t('dashboards.edit.move')} title={t('dashboards.edit.moveHint')}
                  onPointerDown={drag(i, 'move')} onKeyDown={keys(i)}><IconGripVertical size={16} /></button>
                <span className="fb-grid-corner" aria-hidden="true" onPointerDown={drag(i, 'size')} />
                {sizing === i && <span className="fb-grid-size" role="status">{t('dashboards.edit.cells', { w: p.w, h: p.h })}</span>}
              </>
            )}
          </div>
        )
      })}
      {editing && !section.panels.length && <Text size="sm" c="dimmed" className="fb-grid-empty">{t('dashboards.section.empty')}</Text>}
    </div>
  )
}
