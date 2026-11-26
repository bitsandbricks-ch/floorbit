import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const SeatMapping = lazy(() => import('@/pages/SeatMapping'))
const SeatWalk = lazy(() => import('@/pages/SeatWalk'))
const SwitchAreas = lazy(() => import('@/pages/SwitchAreas'))
const SwitchSwap = lazy(() => import('@/pages/SwitchSwap'))
const Checkins = lazy(() => import('@/pages/Checkins'))
const Endpoints = lazy(() => import('@/pages/Endpoints'))

export const routes: AppRoute[] = [
  { path: '/seat-mapping', element: createElement(SeatMapping) },
  { path: '/seat-walk', element: createElement(SeatWalk) },
  { path: '/switch-areas', element: createElement(SwitchAreas) },
  { path: '/switch-swap/:id', element: createElement(SwitchSwap) },
  { path: '/checkins', element: createElement(Checkins) },
  { path: '/endpoints', element: createElement(Endpoints) },
]
