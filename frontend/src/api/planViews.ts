// Saved floor plan views (floorbit/plan_views.py): a hall shown a certain way, under a name.
import { useQuery } from '@tanstack/react-query'
import { get } from './client'

export interface PlanView {
  id: string
  name: string
  hall: string
  /** Where the plan looks, in drawing units. */
  view: { x: number; y: number; w: number; h: number }
  /** The plan address's ``layers`` and ``fade`` (pages/plan/layers.ts); no layers is the default set. */
  layers?: string
  fade?: string
  show: 'all' | 'problems' | 'offline' | 'recent' | 'note' | 'checked_in'
  /** Only the person who saved it sees it. */
  private: boolean
  by?: string
  saved: string
}

export type PlanViewFields = Omit<PlanView, 'id' | 'by' | 'saved'>

export const PLAN_VIEWS_KEY = ['plan-views'] as const

/** The views you see, of every hall (a handful per hall: one list serves the menu and the dashboards). */
export function usePlanViews(enabled = true) {
  return useQuery({
    queryKey: PLAN_VIEWS_KEY, queryFn: () => get<{ views: PlanView[] }>('/api/plan-views'),
    staleTime: 60_000, enabled, select: (d) => d.views,
  })
}
