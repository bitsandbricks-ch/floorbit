// API tokens (auth/tokens.py, floorbit/blueprints/api_tokens.py)
/** One audit log line (floorbit/audit.py): names what changed, never the values. */
export interface AuditEntry {
  time: string
  user: string | null
  area: string
  action: string
  target?: string
  fields?: string[]
  ok?: boolean
}

export interface AuditPage {
  entries: AuditEntry[]
  total: number
  areas: string[]
}
