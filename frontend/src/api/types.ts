// Shapes the Flask API returns. Keep in step with floorbit/plugins and auth.
// Each area's shapes live in src/api/<area>.ts next to its queries (issue #1233); this file keeps
// the few every page shares and re-exports the rest, so `from '../api/types'` keeps working.
// A new area adds its own file and imports from it, not a line here.
export * from './accounts'
export * from './agents'
export * from './apiTokens'
export * from './audit'
export * from './cables'
export * from './checkin'
export * from './commands'
export * from './configs'
export * from './crew'
export * from './dns'
export * from './endpoints'
export * from './features'
export * from './firewalls'
export * from './floorPlan'
export * from './flows'
export * from './gameServers'
export * from './games'
export * from './halls'
export * from './health'
export * from './incidents'
export * from './inventory'
export * from './lancache'
export * from './logs'
export * from './notice'
export * from './pastEvents'
export * from './plan'
export * from './plugins'
export * from './portClients'
export * from './power'
export * from './preflight'
export * from './problems'
export * from './replay'
export * from './report'
export * from './schedule'
export * from './seatMap'
export * from './security'
export * from './services'
export * from './setup'
export * from './speedtest'
export * from './stats'
export * from './statusPage'
export * from './switchAreas'
export * from './timeline'
export * from './topology'
export * from './traffic'
export * from './walkThrough'
export * from './webhooks'
export * from './wifi'

/** A permission from auth/roles.py PERMISSIONS, e.g. 'floorplan.edit'. */
export type Permission = string

export interface User {
  username: string
  display_name: string
  /** admin, lead, tech, viewer, kiosk or a custom role. */
  role: string
  role_label?: string
  permissions: Permission[]
  /** A platform admin visiting this tenant, with no account here (floorbit/tenant_switch.py). */
  platform?: boolean
}

export interface Me {
  enabled: boolean
  user: User | null
}

export type Tone = '' | 'ok' | 'warn' | 'err'
export type State = 'up' | 'down' | 'warn' | 'unknown'

export interface LogLine {
  time: string
  line: string
}

/** A page for the "Go to" palette, from GET /api/pages (issues #242, #250): the server picks the
 *  pages this account may open with the features and set-up this event has, so the floor plan,
 *  Settings and the React pages all offer the same list. */
export interface PageLink {
  href: string
  /** Key under goto.pages in the i18n files; ``label`` is the English fallback. */
  id: string
  label: string
}

/** A seat or switch for "Go to", from GET /api/pages/find (issue #252). */
export interface Place {
  /** player: a nick, IP or MAC and its seat, only for seats.view (issue #292); endpoint: where an
   *  IP or MAC was seen, from the history (also seats.view). */
  kind: 'seat' | 'switch' | 'player' | 'endpoint'
  name: string
  href: string
}
