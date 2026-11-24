import type { SeatViewData } from '@/api/types'

/** Whether a hall has nothing on it yet: no seats, switches, marks, panels or background. Power boards
 *  don't count: every hall shows them. */
export function hallIsEmpty(data: SeatViewData): boolean {
  return !data.blocks.length && !data.switches.length && !data.drawing?.marks?.length && !data.panels?.length
    && !data.background
}
