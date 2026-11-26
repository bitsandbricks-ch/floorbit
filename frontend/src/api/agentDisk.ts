/** What an agent keeps on its disk against its one budget (floorbit/disk_budget.py ``clean``, #1485). */
export interface AgentDisk {
  /** Bytes; missing when the agent could not tell its free space. */
  budget?: number
  used?: number
  /** No budget set: half of what its disk could hold. */
  auto: boolean
  /** Per kind ("flows", "buffer", a plugin's): bytes, files, hours back to the oldest, files overwritten. */
  kinds: Record<string, { bytes?: number; files?: number; hours?: number; dropped?: number }>
}
