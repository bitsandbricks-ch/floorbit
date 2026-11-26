import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Firewalls = lazy(() => import('@/pages/Firewalls'))
const Switches = lazy(() => import('@/pages/Switches'))
const Telemetry = lazy(() => import('@/pages/Telemetry'))
const ViewPage = lazy(() => import('@/pages/monitoring/ViewPage'))

export const routes: AppRoute[] = [
  { path: '/switches', element: createElement(Switches) },
  { path: '/firewalls', element: createElement(Firewalls) },
  { path: '/telemetry', element: createElement(Telemetry) },
  { path: '/wifi', element: createElement(ViewPage, { key: 'wifi', view: 'wifi' }) },
]
