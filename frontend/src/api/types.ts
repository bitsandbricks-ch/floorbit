// Shapes the Flask API returns. Keep in step with floorbit/plugins and auth.

export type Role = 'viewer' | 'editor' | 'admin'

export interface User {
  username: string
  display_name: string
  role: Role
}

export interface Me {
  enabled: boolean
  user: User | null
}

export type Tone = '' | 'ok' | 'warn' | 'err'
export type State = 'up' | 'down' | 'warn' | 'unknown'

interface WidgetBase {
  id: string
  label: string
  size: 'small' | 'wide'
  refresh: number
  sub: string
  link: string
}

export type Widget = WidgetBase &
  (
    | { type: 'stat'; value: number | string; unit: string; tone: Tone }
    | { type: 'status'; items: { label: string; state: State; detail: string }[] }
    | { type: 'list'; items: { label: string; value: string; tone: Tone }[] }
    | {
        type: 'table'
        columns: { key: string; label: string }[]
        rows: Record<string, string>[]
      }
    | { type: 'sparkline'; points: number[]; value?: number; min?: number; max?: number; unit: string }
  )

export interface WidgetTile {
  kind?: undefined
  plugin: string
  plugin_name: string
  id: string
  label: string
  size: 'small' | 'wide'
  refresh: number
  url: string
}

export interface ActionTile {
  kind: 'action'
  plugin: string
  plugin_name: string
  id: string
  label: string
  danger: boolean
  url: string
}

export type Tile = WidgetTile | ActionTile

export interface ActionResult {
  ok: boolean
  message: string
  data: Record<string, unknown>
}

export interface PluginInfo {
  id: string
  name: string
  version: string
  description: string
  trust: 'builtin' | 'development' | string
  author: string
  homepage: string
  uses: { id: string; label: string }[]
  enabled: boolean
  error: string | null
  settings_section: string | null
  actions: { id: string; label: string; role: Role; danger?: boolean; help?: string }[]
  widgets: { id: string; label: string; size: string; refresh: number; role: Role }[]
  endpoints: { id: string; label: string; url: string }[]
  hooks: { events: string[]; action: string }[]
  has_test: boolean
}

export interface LogLine {
  time: string
  line: string
}
