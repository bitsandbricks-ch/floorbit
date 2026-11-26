import type { LinkType } from './topology'

/** Cables and patching (issue #97). */
export interface Cable {
  id: string; label: string; switch: string; port: string; panel: string; panel_port: string; seat: string
  color: string; length_m: number | null; note: string; source: 'floorbit' | 'import'; plugin?: string
  /** Cable type and speed (issue #468), like the links between switches. */
  type?: LinkType | ''; speed?: number | null
  updated_at: number; by: string | null; block?: string
}
export interface CableList { cables: Cable[]; sources: string[] }
export interface CableImport { imported: number; errors: string[] }
/** A seat block patched to a switch in one go (issue #473). */
export interface PlannedCable { seat: string; switch: string; port: string; block: string }
export interface CableClash {
  seat: string; port: string; kind: 'port' | 'seat'; cable: string; imported: boolean
  other_seat?: string; other_port?: string
}
export interface BlockPlan { rows: string[]; cables: PlannedCable[]; clashes: CableClash[]; created?: number; removed?: number }
export interface PatchRow { switch: string; port: string; seat?: string; cable?: string; state?: string; described_seat?: string }
export interface PatchList { count: number; rows: PatchRow[] }
export interface PatchCheck {
  /** Each hall row's cabled seats and how many are up (#1057). */
  last_poll: number | null; rows: { row: string; name: string; block_label: string; naming: string; seats: number; up: number }[]
  missing: PatchList; down: PatchList; unplanned: PatchList; conflicts: PatchList; unread: string[]
}
