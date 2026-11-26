import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const ViewPage = lazy(() => import('@/pages/monitoring/ViewPage'))
const Applications = lazy(() => import('@/pages/Applications'))
const FlowLookup = lazy(() => import('@/pages/FlowLookup'))

export const routes: AppRoute[] = [
  { path: '/traffic', element: createElement(ViewPage, { key: 'traffic', view: 'traffic' }) },
  { path: '/games', element: createElement(ViewPage, { key: 'games', view: 'games' }) },
  { path: '/dns', element: createElement(ViewPage, { key: 'dns', view: 'dns' }) },
  { path: '/applications', element: createElement(Applications) },
  { path: '/flow-lookup', element: createElement(FlowLookup) },
  { path: '/speedtests', element: createElement(ViewPage, { key: 'speedtests', view: 'speedtests' }) },
]
