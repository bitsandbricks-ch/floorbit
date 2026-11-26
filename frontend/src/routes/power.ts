import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Power = lazy(() => import('@/pages/Power'))
const BoardPage = lazy(() => import('@/pages/power/BoardPage'))
const CircuitPage = lazy(() => import('@/pages/power/CircuitPage'))

export const routes: AppRoute[] = [
  { path: '/power', element: createElement(Power) },
  { path: '/power/boards/:id', element: createElement(BoardPage) },
  { path: '/power/circuits/:id', element: createElement(CircuitPage) },
]
