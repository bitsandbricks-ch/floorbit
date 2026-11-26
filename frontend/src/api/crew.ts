import type { IncidentStatus } from './incidents'
import type { CrewNotice } from './notice'
import type { PlanDrawing } from './plan'

/** GET /api/jobs: the tech's own jobs and duty status (issue #30). Plan points are in the drawing's units. */
export interface DutyStatus { on_duty: boolean; at: string | null; since: number | null }
export interface Job {
  id: string; title: string; seat: string | null; switch_id: string | null; switch_name: string | null
  circuit_id: string | null; circuit_name: string | null; status: IncidentStatus; team: string | null
  source: string; reports: number; created_at: number; dispatched_at: number | null; taken_at: number | null
  notes: { by: string | null; at: number; text: string }[]
  /** The attendee tapped "It works again" on the seat's help page (issue #382). */
  seat_ok_at?: number | null
  drawing: PlanDrawing | null; target: [number, number] | null; from: [number, number] | null; hall: string | null
  /** The steps for this kind of incident, right on the job (issue #102). */
}
export interface JobsData { me: DutyStatus; seats: string[]; jobs: Job[]; can_dispatch: boolean; done?: number; auto?: boolean }
export interface CrewMember { username: string; display_name: string; at: string | null; since: number | null; jobs: number; done?: number }

/** Shift handover (issue #33). */
export interface HandoverIncident {
  id: string; title: string; where: { kind: 'seat' | 'switch' | 'circuit'; name: string }; status: IncidentStatus
  assignee: string | null; team: string | null; created_at: number; fixed_at: number | null
}
export interface HandoverRecord {
  id: string; at: number; since: number; by: string | null; note: string
  counts: HandoverCounts
}
export interface HandoverCounts { open: number; waiting?: number; opened: number; fixed: number; outages: number; still_down: number; changes: number; problems: number; muted?: number; median_fix_s?: number | null }
export interface HandoverData {
  since: number; now: number; previous: HandoverRecord | null
  incidents: { open: HandoverIncident[]; opened: number; fixed: HandoverIncident[] }
  outages: { switch_id: string; name: string; down_at: number; back_at: number | null; down_s: number }[]
  changes: { at: number; user: string | null; area: string; action: string; target: string | null }[]
  /** Crew notes on seats written or changed this shift (issue #202). */
  seat_notes: { seat: string; text: string; by: string | null; at: number }[]
  /** What is muted right now, and the crew notice that is up (issue #258). */
  mutes?: { kind: 'switch' | 'health'; name: string; until: number; by: string | null; reason: string }[]
  notice?: CrewNotice | null
  coming_up?: { id: string; title: string; kind: string; start: number; end: number | null; where: string | null }[]
  counts: HandoverCounts
  history: HandoverRecord[]
  discord: boolean
}
