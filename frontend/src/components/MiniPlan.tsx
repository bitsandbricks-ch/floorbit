import type { ReactNode } from 'react'
import type { PlanDrawing } from '@/api/types'
import { blockTop } from '@/pages/plan/blockTop'
import './MiniPlan.css'

/** A small, read-only drawing of a hall: its seat blocks, seats and block names, for pages that
 *  show where something is (a job, the Wi-Fi, a replay). It fills the width it gets and keeps the
 *  hall's shape, never taller than the screen below the top bar (#936), the same on every page.
 *  ``seat`` gives a seat's extra classes and children; ``over`` is drawn on top. */
export function MiniPlan({ drawing, label, className, frames, seat, defs, children }: {
  drawing: Pick<PlanDrawing, 'box' | 'cell' | 'shapes'>; label: string; className?: string
  /** A dashed frame around each block, as the replay draws them. */
  frames?: boolean
  seat?: (id: string, at: { x: number; y: number }) => { className?: string; children?: ReactNode } | undefined
  defs?: ReactNode; children?: ReactNode
}) {
  const cell = drawing.cell
  return (
    <svg viewBox={drawing.box} role="img" aria-label={label} className={`fb-mini-plan${className ? ` ${className}` : ''}`}>
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
