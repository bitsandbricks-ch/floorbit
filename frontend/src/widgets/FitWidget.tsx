import './widgets.css'
import type { Widget } from '@/api/types'
import { type Kind, type KindPick, type Level, type LevelPin, pickLevel } from './level'
import { BarsKind } from './kinds/Bars'
import { ColumnsKind } from './kinds/Columns'
import { GaugeKind } from './kinds/Gauge'
import { HistogramKind } from './kinds/Histogram'
import { Graph } from './kinds/Graph'
import { PieKind } from './kinds/Pie'
import { RowsKind } from './kinds/Rows'
import { type Look, resolveKind } from './kinds/shape'
import { StatKind } from './kinds/Stat'
import { useBox } from './useBox'

/** A widget that fits its box (issue #924): the kind the pane picked (or the data's own), at the
 *  level the box allows (or the pane pins). Nothing inside scrolls; what doesn't fit is "+N more". */
export function FitWidget({ widget, pick = 'auto', pin = 'auto', look, onMore }: {
  widget: Widget; pick?: KindPick; pin?: LevelPin; look?: Look; onMore?: () => void
}) {
  const [ref, box] = useBox<HTMLDivElement>()
  const kind = resolveKind(widget, pick)
  const level = pickLevel(kind, box.w, box.h, pin)
  return (
    <div className={`fb-w fb-w-is-${kind} fb-w-level-${level}`} data-kind={kind} data-level={level}>
      <div className="fb-w-area" ref={ref}>
        {box.w > 0 && <Kind kind={kind} widget={widget} level={level} box={box} look={look} onMore={onMore} />}
      </div>
      {level !== 's' && widget.sub && <div className="fb-w-sub" title={widget.sub}>{widget.sub}</div>}
    </div>
  )
}

function Kind({ kind, look, ...props }: { kind: Kind; widget: Widget; level: Level; box: { w: number; h: number }; look?: Look; onMore?: () => void }) {
  switch (kind) {
    case 'stat': return <StatKind {...props} />
    case 'gauge': return <GaugeKind {...props} />
    case 'graph': return <Graph {...props} look={look} />
    case 'bar': return <BarsKind {...props} look={look} />
    case 'column': return <ColumnsKind {...props} look={look} />
    case 'histogram': return <HistogramKind {...props} />
    case 'pie': return <PieKind {...props} />
    default: return <RowsKind kind={kind} {...props} />
  }
}
