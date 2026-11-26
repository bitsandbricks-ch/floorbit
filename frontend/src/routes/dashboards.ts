import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Overview = lazy(() => import('@/pages/Overview'))
const Dashboards = lazy(() => import('@/pages/Dashboards'))
const DashboardView = lazy(() => import('@/pages/DashboardView'))
const Widgets = lazy(() => import('@/pages/widgets/Widgets'))

export const routes: AppRoute[] = [
  { path: '/overview', element: createElement(Overview) },
  { path: '/dashboards', element: createElement(Dashboards) },
  { path: '/dashboards/view/:id', element: createElement(DashboardView) },
  { path: '/widgets', element: createElement(Widgets) },
]
