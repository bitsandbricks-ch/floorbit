/** A saved switch command template (floorbit/commands.py, issue #94). */
export interface CommandTemplate {
  id: string
  kind: 'show' | 'change'
  label: string
  commands: string[]
  builtin: boolean
  needs_port: boolean
}

/** GET /api/commands. */
export interface CommandInfo {
  available: boolean
  plugin: string | null
  needs_login: boolean
  platform: string
  templates: CommandTemplate[]
  may_change: boolean
  may_edit: boolean
  switches: string[]
  max_switches: number
}

/** One switch's answer in POST /api/commands/run. */
export interface CommandResult {
  switch: string
  ok: boolean
  output: string
  error: string | null
  ms?: number
}

export interface CommandRun {
  template: string
  label: string
  kind: 'show' | 'change'
  port: string | null
  commands: string[]
  results: CommandResult[]
}

/** GET /api/terminal (floorbit/terminal.py, issue #95). */
export interface TerminalInfo {
  available: boolean
  plugin: string | null
  needs_login: boolean
  switches: string[]
  sessions: { id: string; switch: string; opened: number }[]
  idle_minutes: number
  max_minutes: number
}

/** GET /api/terminal/<id>/output. */
export interface TerminalOutput {
  data: string
  next: number
  skipped: number
  closed: string | null
}
