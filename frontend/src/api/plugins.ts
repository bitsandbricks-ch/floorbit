import type { Permission } from './types'

/** A widget's data, as plugins and Floorbit's own tiles answer it: the shared kit's type. */
export type { Widget } from '@bitsandbricks/ui'

/** A plugin's box in a side panel (GET /api/plugins/panels?on=...). */
export interface PluginPanelInfo {
  plugin: string
  plugin_name: string
  icon: string
  id: string
  label: string
  refresh: number
  url: string
}

/** A plugin's floor plan layer (GET /api/plugins/layers). */
export interface PluginLayerInfo {
  plugin: string
  plugin_name: string
  icon: string
  id: string
  label: string
  refresh: number
  url: string
}

/** One plugin page (GET /api/plugins/<id>/pages/<page>): its tiles this account may see. */
export interface PluginPageData {
  plugin: string
  plugin_name: string
  icon: string
  id: string
  label: string
  columns: number
  tiles: Tile[]
}

export type PluginLayerTone = 'ok' | 'warn' | 'err' | 'info'

/** What one plugin layer draws (GET /api/plugins/<id>/layers/<layer>). */
export interface PluginLayerData {
  seats: Record<string, { tone: PluginLayerTone; label: string }>
  legend: { tone: PluginLayerTone; label: string }[]
}

export interface WidgetTile {
  kind?: undefined
  plugin: string
  plugin_name: string
  id: string
  label: string
  size: 'small' | 'wide'
  refresh: number
  url: string
  /** A pane may pick the time it shows (``?range=``) and compare it (``?compare=``), issue #960. */
  ranges?: boolean
  /** It can mark what happened on its graph (``?marks=1``): switches down, incidents. */
  marks?: boolean
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
  icon?: string
  version: string
  description: string
  trust: 'builtin' | 'development' | 'official' | string
  author: string
  homepage: string
  uses: { id: string; label: string }[]
  enabled: boolean
  error: string | null
  settings_section: string | null
  actions: { id: string; label: string; role: string; permission?: Permission; danger?: boolean; help?: string }[]
  widgets: { id: string; label: string; size: string; refresh: number; role: string; permission?: Permission }[]
  endpoints: { id: string; label: string; url: string }[]
  hooks: { events: string[]; action: string }[]
  has_test: boolean
  /** Set for a plugin with a part on the local agent (``agent:`` in plugin.yaml). */
  agent?: { actions: string[]; calls: string[]; sends: string[] } | null
  /** ``schema:`` of this version, and the schema this tenant's data is at (0: none). */
  schema?: number
  data_schema?: number
}
