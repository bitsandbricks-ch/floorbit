import type { PlanDrawing } from './plan'

/** One frame of the whole-event recording (issue #104). blocks: name -> [seats, online, bps, open incidents]. */
export interface EventFrame {
  t: number
  down: number
  up: number
  online: number
  seats: string[]
  incidents: string[]
  blocks: Record<string, [number, number, number, number]>
}

/** GET /api/replay/event: the whole event of one hall, a frame every 5 minutes, thinned out as it ages. */
export interface EventReplayData {
  halls: { id: string; name: string }[]
  hall: string
  drawing: PlanDrawing | null
  frames: EventFrame[]
  start: number | null
  end: number | null
  step: number
}
