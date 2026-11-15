import type { Permission } from '@/api/types'

/** Every page a crew member may want to jump to, for the "Go to" palette (issue #242).
 *  ``feature`` hides it while that feature is off, ``can`` while the role lacks the permission;
 *  the server checks both again, so this only keeps the list honest. */
export interface PageLink {
  href: string
  /** Key under goto.pages in the i18n files. */
  id: string
  feature?: string
  can?: Permission
}

export const PAGES: PageLink[] = [
  { href: '/', id: 'floorPlan' },
  { href: '/plan', id: 'seats' },
  { href: '/dashboard', id: 'dashboard', feature: 'dashboard' },
  { href: '/problems', id: 'problems' },
  { href: '/incidents', id: 'incidents', feature: 'incidents' },
  { href: '/jobs', id: 'jobs', feature: 'dispatch' },
  { href: '/handover', id: 'handover', feature: 'handover', can: 'incidents.work' },
  { href: '/runbooks', id: 'runbooks', feature: 'runbooks', can: 'incidents.work' },
  { href: '/health', id: 'health', feature: 'health' },
  { href: '/stats', id: 'stats' },
  { href: '/traffic', id: 'traffic', feature: 'traffic' },
  { href: '/dns', id: 'dns', feature: 'dns' },
  { href: '/games', id: 'games', feature: 'games' },
  { href: '/logs', id: 'logs', feature: 'syslog', can: 'seats.view' },
  { href: '/security', id: 'security', feature: 'security', can: 'seats.view' },
  { href: '/wifi', id: 'wifi', feature: 'wifi' },
  { href: '/power', id: 'power', feature: 'power' },
  { href: '/commands', id: 'commands', feature: 'commands', can: 'ports.act' },
  { href: '/terminal', id: 'terminal', feature: 'terminal', can: 'terminal.open' },
  { href: '/inventory', id: 'inventory' },
  { href: '/seat-mapping', id: 'seatMapping', can: 'seats.view' },
  { href: '/cables', id: 'cables', feature: 'cables' },
  { href: '/gear', id: 'gear', feature: 'gear', can: 'incidents.work' },
  { href: '/planner', id: 'planner', feature: 'planner', can: 'floorplan.edit' },
  { href: '/preflight', id: 'preflight', feature: 'preflight' },
  { href: '/teardown', id: 'teardown', feature: 'teardown', can: 'floorplan.edit' },
  { href: '/tournament', id: 'tournament', feature: 'tournament' },
  { href: '/tournament/brackets', id: 'brackets', feature: 'tournament' },
  { href: '/schedule', id: 'schedule', feature: 'schedule' },
  { href: '/timeline', id: 'timeline', feature: 'timeline', can: 'audit.read' },
  { href: '/network-status', id: 'networkStatus', feature: 'status_page' },
  { href: '/replay', id: 'replay', feature: 'replay' },
  { href: '/report', id: 'report', feature: 'report' },
  { href: '/events', id: 'events', feature: 'past_events' },
  { href: '/templates', id: 'templates' },
  { href: '/settings', id: 'settings', can: 'settings.manage' },
  { href: '/settings/plugins', id: 'plugins', can: 'settings.manage' },
  { href: '/settings/features', id: 'features', can: 'settings.manage' },
  { href: '/settings/api', id: 'apiTokens', can: 'settings.manage' },
  { href: '/settings/webhooks', id: 'webhooks', can: 'settings.manage' },
  { href: '/settings/users', id: 'users', can: 'accounts.manage' },
  { href: '/settings/teams', id: 'teams', can: 'accounts.manage' },
  { href: '/settings/sign-in', id: 'signIn', can: 'settings.manage' },
  { href: '/settings/audit', id: 'audit', can: 'audit.read' },
]

/** Lower case without accents, so "ubergabe" finds "Übergabe". */
export function fold(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}
