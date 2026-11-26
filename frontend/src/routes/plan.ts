import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const FloorPlan = lazy(() => import('@/pages/FloorPlan'))

export const routes: AppRoute[] = [
  { path: '/plan', element: createElement(FloorPlan) },
]
