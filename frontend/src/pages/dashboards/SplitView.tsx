import { ActionIcon, Group, Tooltip } from '@mantine/core'
import { IconLayoutColumns, IconLayoutRows, IconSettings, IconTrash } from '@tabler/icons-react'
import { Fragment, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { isPane, type Node, type Path, type Split } from './model'
import { PaneView } from './Panes'

export interface Editing {
  selected: Path | null
  onSelect: (path: Path) => void
  onSplit: (path: Path, dir: Split) => void
  onRemove: (path: Path) => void
  onResize: (path: Path, border: number, pct: number) => void
}

const same = (a: Path | null, b: Path) => !!a && a.length === b.length && a.every((v, i) => v === b[i])

/** A dashboard drawn as nested splits. With ``editing`` each pane gets its tools and the borders
 *  between parts can be dragged. */
export function SplitView({ node, path = [], editing, cycle }: { node: Node; path?: Path; editing?: Editing; cycle?: number }) {
  if (isPane(node)) {
    return (
      <div className={`fb-split-pane${editing && same(editing.selected, path) ? ' selected' : ''}`}>
        <PaneView pane={node.pane} cycle={cycle} />
        {editing && <PaneTools path={path} editing={editing} />}
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

function PaneTools({ path, editing }: { path: Path; editing: Editing }) {
  const { t } = useTranslation()
  return (
    <>
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
