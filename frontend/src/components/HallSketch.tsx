import type { PlanCell, PlanDrawing } from '@/api/types'
import { blockTop } from '@/pages/plan/blockTop'
import { PlanMarks } from '@/pages/plan/PlanMarks'

/** A hall's seat blocks with its walls, zones, labels and icons, as the public pages draw it from
 *  ``floorbit/blueprints/screen.py`` ``plan()``: the attendee view colours the online seats, the
 *  seat finder rings the one seat found. */
export function HallSketch({ drawing, label, cellClass, ring }: {
  drawing: PlanDrawing; label: string
  cellClass: (c: PlanCell) => string
  /** Draw a ring round the cells this says yes to. */
  ring?: (c: PlanCell) => boolean
}) {
  const d = drawing
  return (
    <svg viewBox={d.box} role="img" aria-label={label} className="fb-hall-sketch">
      <PlanMarks drawing={d} />
      {d.shapes.map((b, i) => (
        <g key={b.id ?? i}>
          <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
            <rect className="blk" x={-b.w / 2 - 6} y={-b.h / 2 - 6} width={b.w + 12} height={b.h + 12} rx={6} />
            {b.cells.map((c) => (
              <rect key={c.seat} className={`cell ${cellClass(c)}`} data-seat={c.seat} x={c.x + 1} y={c.y + 1}
                width={d.cell - 2} height={d.cell - 2} rx={3}><title>{c.seat}</title></rect>
            ))}
            {ring && b.cells.filter(ring).map((c) => (
              <circle key={`ring-${c.seat}`} className="ring" cx={c.x + d.cell / 2} cy={c.y + d.cell / 2} r={d.cell * 1.4} />
            ))}
            {(b.rows ?? []).map((r, n) => (
              <text key={n} className="rowlbl" x={r.x} y={r.y} dy="0.35em"
                transform={b.rotation ? `rotate(${-b.rotation} ${r.x} ${r.y})` : undefined}>{r.text}</text>
            ))}
          </g>
          {b.name && <text className="name" x={b.cx} y={blockTop(b) - 18}>{b.name}</text>}
        </g>
      ))}
    </svg>
  )
}
