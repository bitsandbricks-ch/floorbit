/** GET /api/events (issue #38): the running event and the archived ones, for comparing. */
export interface EventFigures {
  seats: number
  online_max: number
  checked_in_max: number
  peak_bps: number | null
  bytes_moved: number
  hours: number
  incidents: number
  incidents_fixed: number
  from_seats: number
  median_fix_s: number | null
  /** From reported to first taken by someone (issue #294); null for events archived before it. */
  median_take_s: number | null
  outages: number
  down_s: number
  problem_ports: number
  cache_saved_bytes: number | null
}

export interface PastEvent {
  id: string
  name: string
  start: number | null
  end: number | null
  archived_at: number
  archived_by: string | null
  figures: EventFigures
}

export interface EventsData {
  current: { name: string; start: number | null; end: number | null; figures: EventFigures }
  archived: PastEvent[]
}
