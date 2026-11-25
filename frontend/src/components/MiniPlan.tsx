import type { ReactNode } from 'react'
import type { PlanDrawing } from '@/api/types'
import { blockTop } from '@/pages/plan/blockTop'
import { contentBox } from '@/pages/dashboards/model'
import './MiniPlan.css'

/** A small, read-only drawing of a hall: its seat blocks, seats and block names, for pages that
 *  show where something is (a job, the Wi-Fi, a replay). It fills the width it gets and keeps the
 *  hall's shape, never taller than the screen below the top bar (#936), the same on every page.
 *  It shows only the part of the hall with something in it (the blocks and ``points``),
 *  not the empty floor around. ``seat`` gives a seat's extra classes and children; ``children`` are
 *  drawn on top. */
export function MiniPlan({ drawing, label, className, frames, seat, points = [], defs, children }: {
  drawing: Pick<PlanDrawing, 'box' | 'cell' | 'shapes'>; label: string; className?: string
  /** More places to keep in view, such as access points or where the tech stands. */
  points?: [number, number][]
  /** A dashed frame around each block, as the replay draws them. */
  frames?: boolean
  seat?: (id: string, at: { x: number; y: number }) => { className?: string; children?: ReactNode } | undefined
  defs?: ReactNode; children?: ReactNode
}) {
  const cell = drawing.cell
  return (
    <svg viewBox={viewBox(drawing, points)} role="img" aria-label={label} className={`fb-mini-plan${className ? ` ${className}` : ''}`}>
      {defs && <defs>{defs}</defs>}
      {drawing.shapes.map((b, i) => (
        <g key={i}>
          <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
            {frames && <rect className="blk" x={-b.w / 2 - 6} y={-b.h / 2 - 6} width={b.w + 12} height={b.h + 12} rx={6} />}
            {b.cells.map((c) => {
              const own = seat?.(c.seat, { x: c.x + cell / 2, y: c.y + cell / 2 })
              return (
                <g key={c.seat}>
                  <rect className={`cell${own?.className ? ` ${own.className}` : ''}`} data-seat={c.seat}
                    x={c.x + 1} y={c.y + 1} width={cell - 2} height={cell - 2} rx={3}>
                    <title>{c.seat}</title>
                  </rect>
                  {own?.children}
                </g>
              )
            })}
          </g>
          {b.name && <text className="name" x={b.cx} y={blockTop(b) - 12}>{b.name}</text>}
        </g>
      ))}
      {children}
    </svg>
  )
}

/** The blocks, marks and points with a margin, or the whole drawing when there is nothing in it. */
function viewBox(drawing: Parameters<typeof MiniPlan>[0]['drawing'], points: [number, number][], margin = 80): string {
  // Marks aren't drawn here, so the walls around the hall don't count.
  const c = contentBox({ shapes: drawing.shapes })
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1])
  if (c) { xs.push(c.x, c.x + c.w); ys.push(c.y, c.y + c.h) }
  if (!xs.length) return drawing.box
  const x0 = Math.min(...xs) - (points.length ? margin : 0), y0 = Math.min(...ys) - (points.length ? margin : 0)
  const x1 = Math.max(...xs) + (points.length ? margin : 0), y1 = Math.max(...ys) + (points.length ? margin : 0)
  return `${x0} ${y0} ${x1 - x0} ${y1 - y0}`
}
