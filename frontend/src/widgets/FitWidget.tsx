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
import { NumberStyleContext } from './kinds/display'
import { StatKind } from './kinds/Stat'
import { useBox } from './useBox'
import { LevelReport } from './levelReport'
import { useContext, useEffect } from 'react'

const NO_STYLE = {}
/** The sub line under a widget: its 12px text plus the 4px gap (widgets.css). */
const SUB_H = 20

/** A widget that fits its box (issue #924): the kind the pane picked (or the data's own), at the
 *  level the box allows (or the pane pins). Nothing inside scrolls; what doesn't fit is "+N more". */
export function FitWidget({ widget, pick = 'auto', pin = 'auto', look, onMore }: {
  widget: Widget; pick?: KindPick; pin?: LevelPin; look?: Look; onMore?: () => void
}) {
  // The level comes from the whole widget, which doesn't change with the level. Measuring only the
  // drawing area flapped (issue #1010): at M the sub line takes room, the area shrinks below M,
  // S hides the sub line, the area grows back to M, and so on.
  const [ref, whole] = useBox<HTMLDivElement>()
  const kind = resolveKind(widget, pick)
  const level = pickLevel(kind, whole.w, whole.h, pin)
  const report = useContext(LevelReport)
  useEffect(() => { if (whole.w) report?.(level) }, [report, level, whole.w])
  // A stat with nothing to show ("–") keeps its sub line even when small: it says why.
  const empty = widget.type === 'stat' && widget.value === '–'
  const sub = !!widget.sub && (level !== 's' || empty)
  const box = { w: whole.w, h: Math.max(0, whole.h - (sub ? SUB_H : 0)) }
  return (
    <NumberStyleContext.Provider value={look?.number ?? NO_STYLE}>
    <div className={`fb-w fb-w-is-${kind} fb-w-level-${level}${look?.text ? ` fb-w-text-${look.text}` : ''}`} data-kind={kind} data-level={level} ref={ref}>
      <div className="fb-w-area">
        {box.w > 0 && <Kind kind={kind} widget={widget} level={level} box={box} look={look} onMore={onMore} />}
      </div>
      {sub && <div className="fb-w-sub" title={widget.sub}>{widget.sub}</div>}
    </div>
    </NumberStyleContext.Provider>
  )
}

function Kind({ kind, look, ...props }: { kind: Kind; widget: Widget; level: Level; box: { w: number; h: number }; look?: Look; onMore?: () => void }) {
  switch (kind) {
    case 'stat': return <StatKind {...props} look={look} />
    case 'gauge': return <GaugeKind {...props} />
    case 'graph': return <Graph {...props} look={look} />
    case 'bar': return <BarsKind {...props} look={look} />
    case 'column': return <ColumnsKind {...props} look={look} />
    case 'histogram': return <HistogramKind {...props} />
    case 'pie': return <PieKind {...props} />
    default: return <RowsKind kind={kind} {...props} />
  }
}
