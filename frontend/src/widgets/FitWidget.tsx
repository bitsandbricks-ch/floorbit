import './widgets.css'
import type { Widget } from '@/api/types'
import { type KindPick, type LevelPin, pickLevel } from './level'
import { Graph } from './kinds/Graph'
import { RowsKind } from './kinds/Rows'
import { resolveKind } from './kinds/shape'
import { StatKind } from './kinds/Stat'
import { useBox } from './useBox'

/** A widget that fits its box (issue #924): the kind the pane picked (or the data's own), at the
 *  level the box allows (or the pane pins). Nothing inside scrolls; what doesn't fit is "+N more". */
export function FitWidget({ widget, pick = 'auto', pin = 'auto', onMore }: {
  widget: Widget; pick?: KindPick; pin?: LevelPin; onMore?: () => void
}) {
  const [ref, box] = useBox<HTMLDivElement>()
  const kind = resolveKind(widget, pick)
  const level = pickLevel(kind, box.w, box.h, pin)
  return (
    <div className={`fb-w fb-w-${kind} fb-w-level-${level}`} data-kind={kind} data-level={level}>
      <div className="fb-w-area" ref={ref}>
        {box.w > 0 && (kind === 'stat' ? <StatKind widget={widget} level={level} box={box} />
          : kind === 'graph' ? <Graph widget={widget} level={level} box={box} />
            : <RowsKind widget={widget} kind={kind} level={level} box={box} onMore={onMore} />)}
      </div>
      {level !== 's' && widget.sub && <div className="fb-w-sub" title={widget.sub}>{widget.sub}</div>}
    </div>
  )
}
