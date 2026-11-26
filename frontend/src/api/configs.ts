/** One kept switch config (floorbit/config_backup.py, issue #96). */
export interface ConfigCopy {
  id: string
  at: number
  by: string
  sha: string
  lines: number
}

export interface ConfigRow {
  switch: string
  copies: number
  last: ConfigCopy | null
  checked: { at: number; by: string } | null
  baseline: ConfigCopy | null
  changed: boolean
}

/** GET /api/configs. */
export interface ConfigOverview {
  available: boolean
  plugin: string | null
  needs_login: boolean
  switches: ConfigRow[]
  keep: number
  max_switches: number
  /** The backup every night with the stored switch logins. */
  nightly: ConfigNightly
}
export interface ConfigNightly {
  /** Server hour (0-23), or null when it's off. */
  hour: number | null
  covered: number
  switches: number
  last: { at: number; switches: number; ok: number; changed: string[]; failed: { switch: string; error: string }[] } | null
}

/** GET /api/configs/<switch>. */
export interface ConfigHistory {
  switch: string
  copies: ConfigCopy[]
  baseline: string | null
  checked: { at: number; by: string } | null
}

/** GET /api/configs/<switch>/diff. */
export interface ConfigDiff {
  from: ConfigCopy
  to: ConfigCopy
  lines: string[]
  added: number
  removed: number
}

export interface ConfigBackupResult {
  switch: string
  ok: boolean
  error: string | null
  copy?: ConfigCopy
  changed?: boolean
}
