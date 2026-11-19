import { type ComponentType, type LazyExoticComponent, lazy } from 'react'

/** Rich widgets ("views"): a chart, a map, a table with filters, more than the data widgets
 *  (WidgetBody.tsx) can draw. A Dashboard pane shows one (pane kind ``view``), and a widget opened
 *  to its expanded size is the same component with ``expanded``. One line per view below; the
 *  component lives with its feature (``pages/<area>/...View.tsx``) and has no page or route of its own. */
export interface ViewProps {
  /** Shown big (a pane of its own, or a widget opened up): room for filters, search and actions. */
  expanded: boolean
}

export interface ViewDef {
  id: string
  /** Groups views in the Widgets gallery and the pane settings: network, services, traffic, ... */
  area: string
  /** i18n key of its name. */
  label: string
  /** The permission it needs (auth/roles.py); the server checks its data calls either way. */
  permission?: string
  load: () => Promise<{ default: ComponentType<ViewProps> }>
}

export const VIEWS: ViewDef[] = [
  { id: 'lancache', area: 'services', label: 'lancache.title', load: () => import('@/pages/lancache/LancacheView') },
  { id: 'agents', area: 'network', label: 'agents.title', permission: 'settings.manage', load: () => import('@/pages/agents/AgentsView') },
]

/** Each view's component, loaded on first use. */
export const VIEW_COMPONENTS: Record<string, LazyExoticComponent<ComponentType<ViewProps>>> =
  Object.fromEntries(VIEWS.map((v) => [v.id, lazy(v.load)]))
