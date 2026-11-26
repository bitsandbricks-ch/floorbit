import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Events = lazy(() => import('@/pages/Events'))
const Schedule = lazy(() => import('@/pages/Schedule'))
const Timeline = lazy(() => import('@/pages/Timeline'))
const Replay = lazy(() => import('@/pages/Replay'))
const Report = lazy(() => import('@/pages/Report'))
const Templates = lazy(() => import('@/pages/Templates'))

export const routes: AppRoute[] = [
  { path: '/events', element: createElement(Events) },
  { path: '/schedule', element: createElement(Schedule) },
  { path: '/timeline', element: createElement(Timeline) },
  { path: '/replay', element: createElement(Replay) },
  { path: '/report', element: createElement(Report) },
  { path: '/templates', element: createElement(Templates) },
]
