import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Cables = lazy(() => import('@/pages/Cables'))
const WalkRow = lazy(() => import('@/pages/WalkRow'))
const CablePage = lazy(() => import('@/pages/cables/CablePage'))

export const routes: AppRoute[] = [
  { path: '/cables', element: createElement(Cables) },
  { path: '/cables/walk', element: createElement(WalkRow) },
  { path: '/cables/:id', element: createElement(CablePage) },
]
