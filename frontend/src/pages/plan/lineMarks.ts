import type { PlanMark } from '@/api/types'

/** Walls and walkways (#1564) are both drawn from one end to the other, with bends between. */
export const isLine = (m: Pick<PlanMark, 'kind'>) => m.kind === 'wall' || m.kind === 'walkway'

/** A walkway's width when it doesn't say (floorbit/plan_marks.py WALKWAY_DEFAULT), in seats. */
export const WALKWAY_DEFAULT = 2
export const WALKWAY_MIN = 0.5
export const WALKWAY_MAX = 20

/** How wide a walkway is drawn, in drawing units: its width in seats times the seat ``cell``. */
export const walkwayWide = (m: PlanMark, cell: number) => (m.width ?? WALKWAY_DEFAULT) * cell
