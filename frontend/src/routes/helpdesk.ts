import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Incidents = lazy(() => import('@/pages/Incidents'))
const HelpdeskQr = lazy(() => import('@/pages/HelpdeskQr'))
const IncidentPage = lazy(() => import('@/pages/incidents/IncidentPage'))
const Problems = lazy(() => import('@/pages/Problems'))
const ProblemPage = lazy(() => import('@/pages/ProblemPage'))
const Handover = lazy(() => import('@/pages/Handover'))
const NetworkStatus = lazy(() => import('@/pages/NetworkStatus'))

export const routes: AppRoute[] = [
  { path: '/incidents', element: createElement(Incidents) },
  { path: '/incidents/qr', element: createElement(HelpdeskQr) },
  { path: '/incidents/:id', element: createElement(IncidentPage) },
  { path: '/problems', element: createElement(Problems) },
  { path: '/problems/:id', element: createElement(ProblemPage) },
  { path: '/handover', element: createElement(Handover) },
  { path: '/network-status', element: createElement(NetworkStatus) },
]
