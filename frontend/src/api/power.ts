// Electrics: boards, circuits and their load (floorbit/power.py).
export type PowerState = 'ok' | 'warn' | 'crit' | 'tripped' | 'unknown'
export type Phase = 'L1' | 'L2' | 'L3' | '3P'
export interface PowerBoard {
  id: string
  name: string
  location: string
  x: number | null
  y: number | null
}
export interface PowerReading {
  amps: number
  at: number
  source: 'manual' | 'plugin'
  by?: string | null
  plugin?: string
}
export interface CircuitFeed {
  block: string
  rows: number[]
}
export interface Circuit {
  id: string
  board: string
  name: string
  phase: Phase
  rating_a: number
  meter: string
  blocks: CircuitFeed[]
  switches: string[]
  tripped: { by: string | null; at: number } | null
  reading: PowerReading | null
  state: PowerState
  load_pct: number | null
  fed: { seats: string[]; switches: { id: string; name: string }[] }
  /** English, for logs and incidents; the page words feeds_parts (power/feeds.ts). */
  feeds_label: string
  feeds_parts: CircuitFeedParts[]
}
/** One feed of a circuit: the block's label (null once removed) and the rows' names. */
export interface CircuitFeedParts {
  block: string | null
  rows: string[]
  by_rows: boolean
}
export interface PowerOverview {
  enabled: boolean
  boards: PowerBoard[]
  circuits: Circuit[]
  counts: Record<PowerState, number>
  warn: number
  crit: number
  last_poll: number | null
  plugins: number
  /** label: the name, or the row letters of a block named by its rows; row_names: each row, top first. */
  blocks: { id: string; name: string; label: string; rows: number; row_names: string[]; row_ids?: number[] }[]
  can_edit: boolean
  can_read: boolean
}
