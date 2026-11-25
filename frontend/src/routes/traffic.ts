import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const ViewPage = lazy(() => import('@/pages/monitoring/ViewPage'))
const Applications = lazy(() => import('@/pages/Applications'))

export const routes: AppRoute[] = [
  { path: '/traffic', element: createElement(ViewPage, { key: 'traffic', view: 'traffic' }) },
  { path: '/games', element: createElement(ViewPage, { key: 'games', view: 'games' }) },
  { path: '/applications', element: createElement(Applications) },
  { path: '/stats', element: createElement(ViewPage, { key: 'stats', view: 'stats' }) },
  { path: '/speedtests', element: createElement(ViewPage, { key: 'speedtests', view: 'speedtests' }) },
]
