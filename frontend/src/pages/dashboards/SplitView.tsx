import { ActionIcon, Group, Tooltip } from '@mantine/core'
import { IconLayoutColumns, IconLayoutRows, IconSettings, IconTrash } from '@tabler/icons-react'
import { Fragment, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { isPane, type Node, type Path, type Split } from './model'
import { PaneView } from './Panes'
import { PaneKey } from './large'
import { LevelReport, type PaneFit } from '@/widgets/levelReport'
import type { Level } from '@/widgets/level'

export interface Editing {
  selected: Path | null
  onSelect: (path: Path) => void
  onSplit: (path: Path, dir: Split) => void
  onRemove: (path: Path) => void
  onResize: (path: Path, border: number, pct: number) => void
  /** The picked pane says how it draws, for the settings panel. */
  onFit?: (fit: PaneFit | null) => void
}

const same = (a: Path | null, b: Path) => !!a && a.length === b.length && a.every((v, i) => v === b[i])

/** A dashboard drawn as nested splits. With ``editing`` each pane gets its tools and the borders
 *  between parts can be dragged. */
export function SplitView({ node, path = [], editing, cycle }: { node: Node; path?: Path; editing?: Editing; cycle?: number }) {
  // The grid cell's key; the pane's own adds its place in the splits ("make large", ?w=).
  const base = useContext(PaneKey)
  // In the editor, the level the widget drew at, shown on the pane while its box changes (#928).
  const [level, setLevel] = useState<Level | null>(null)
  const [tight, setTight] = useState(false)
  const [rows, setRows] = useState<[number, number] | null>(null)
  const report = useMemo(() => ({ level: (l: Level, small: boolean) => { setLevel(l); setTight(small) }, rows: (shown: number, total: number) => setRows([shown, total]) }), [])
  const picked = !!editing && isPane(node) && same(editing.selected, path)
  const onFit = editing?.onFit
  const cut = level === 'm' ? rows : null
  useEffect(() => {
    if (picked && onFit) onFit(level ? { level, tight, rows: cut } : null)
  }, [picked, onFit, level, tight, cut?.[0], cut?.[1]])   // eslint-disable-line react-hooks/exhaustive-deps
  if (isPane(node)) {
    return (
      <div className={`fb-split-pane${editing && same(editing.selected, path) ? ' selected' : ''}`}>
        <PaneKey.Provider value={base == null ? null : [base, ...path].join('.')}>
          <LevelReport.Provider value={editing ? report : null}>
            <PaneView pane={node.pane} cycle={cycle} />
          </LevelReport.Provider>
        </PaneKey.Provider>
        {editing && <PaneTools path={path} editing={editing} level={level} tight={tight} rows={level === 'm' ? rows : null} />}
      </div>
    )
  }
  return <SplitBox node={node} path={path} editing={editing} cycle={cycle} />
}

function SplitBox({ node, path, editing, cycle }: { node: Extract<Node, { split: Split }>; path: Path; editing?: Editing; cycle?: number }) {
  const box = useRef<HTMLDivElement>(null)
  const drag = (border: number) => (e: React.PointerEvent<HTMLDivElement>) => {
    if (!editing || !box.current) return
    e.preventDefault()
    const el = e.currentTarget
    el.setPointerCapture(e.pointerId)
    const rect = box.current.getBoundingClientRect()
    const move = (ev: PointerEvent) => {
      const pct = node.split === 'row' ? ((ev.clientX - rect.left) / rect.width) * 100 : ((ev.clientY - rect.top) / rect.height) * 100
      editing.onResize(path, border, pct)
    }
    const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up) }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
  }
  return (
    <div ref={box} className={`fb-split fb-split-${node.split}`}>
      {node.children.map((child, i) => (
        <Fragment key={i}>
          {i > 0 && (
            <div className={`fb-split-border${editing ? ' movable' : ''}`} onPointerDown={drag(i - 1)}
              role={editing ? 'separator' : undefined} aria-orientation={node.split === 'row' ? 'vertical' : 'horizontal'} />
          )}
          <div className="fb-split-part" style={{ flexBasis: `${node.sizes[i]}%` }}>
            <SplitView node={child} path={[...path, i]} editing={editing} cycle={cycle} />
          </div>
        </Fragment>
      ))}
    </div>
  )
}

function PaneTools({ path, editing, level, tight, rows }: {
  path: Path; editing: Editing; level: Level | null; tight: boolean; rows: [number, number] | null
}) {
  const { t } = useTranslation()
  // A list that doesn't fit says so, so the box can be made bigger before the screen shows "+N more".
  const cut = rows && rows[0] < rows[1]
  // Below small the widget is cut off on the wall; say so while the box can still grow.
  const warn = tight || cut
  return (
    <>
      {level && (
        <span className={`fb-pane-level${warn ? ' cut' : ''}${tight ? ' tight' : ''}`} data-level={level}>
          {/* A box too small for anything has no room for more than the warning. */}
          {tight ? t('dashboards.edit.tooSmall') : t(`dashboards.level.${level}`)}
          {!tight && cut && ` · ${t('dashboards.edit.rowsShown', { shown: rows[0], total: rows[1] })}`}
        </span>
      )}
      {/* The whole pane picks it for the settings, over whatever the pane shows. */}
      <button type="button" className="fb-pane-pick" aria-label={t('dashboards.edit.pick')} onClick={() => editing.onSelect(path)} />
      <Group gap={4} className="fb-pane-tools">
        <Tooltip label={t('dashboards.edit.settings')}><ActionIcon variant="default" aria-label={t('dashboards.edit.settings')} onClick={() => editing.onSelect(path)}><IconSettings size={16} /></ActionIcon></Tooltip>
        <Tooltip label={t('dashboards.edit.splitRight')}><ActionIcon variant="default" aria-label={t('dashboards.edit.splitRight')} onClick={() => editing.onSplit(path, 'row')}><IconLayoutColumns size={16} /></ActionIcon></Tooltip>
        <Tooltip label={t('dashboards.edit.splitDown')}><ActionIcon variant="default" aria-label={t('dashboards.edit.splitDown')} onClick={() => editing.onSplit(path, 'column')}><IconLayoutRows size={16} /></ActionIcon></Tooltip>
        <Tooltip label={t('dashboards.edit.remove')}><ActionIcon variant="default" color="down" aria-label={t('dashboards.edit.remove')} onClick={() => editing.onRemove(path)}><IconTrash size={16} /></ActionIcon></Tooltip>
      </Group>
    </>
  )
}
