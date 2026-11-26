export interface ManualSeat {
  seat: string
  switch: string
  port: string
  ip: string
  mac: string
  nick: string
  note: string
  updated_at: string | null
  updated_by: string | null
}

export interface SeatRow {
  seat: string
  /** The key: the switch port the seat is on. IP and MAC are read off it. */
  switch: string
  port: string
  /** Where the port came from: typed in, a cable, or a check-in. */
  port_origin: '' | 'manual' | 'cable' | 'checkin'
  ip: string
  mac: string
  nick: string
  from: Partial<Record<'switch' | 'port' | 'ip' | 'mac' | 'nick' | 'note', string>>
  manual: ManualSeat | null
  sources: string[]
  /** On a seat block of any hall; off-plan rows come only from a source (seats.json, a CSV feed). */
  on_plan: boolean
  /** The seat block it is in; empty off the plan (issue #872). */
  block?: string
}

export interface SeatMapList {
  seats: SeatRow[]
  sources: string[]
  errors: Record<string, string>
  labels: Record<string, string>
}

export interface FoundPort {
  switch: string
  port: string
  ip: string
  mac: string
  held_by: string | null
}

export interface ResolvePortsResult {
  dry_run: boolean
  found: Record<string, { switch: string; port: string }>
  missed: string[]
  taken: { seat: string; held_by: string; switch: string; port: string }[]
}

export interface ImportResult {
  dry_run?: boolean
  added: number
  updated: number
  removed: number
}
