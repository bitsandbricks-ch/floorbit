import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Login = lazy(() => import('@/pages/Login'))
const Checkin = lazy(() => import('@/pages/Checkin'))
const PublicStatus = lazy(() => import('@/pages/public/PublicStatus'))
const SeatHelp = lazy(() => import('@/pages/public/SeatHelp'))
const DashboardScreen = lazy(() => import('@/pages/DashboardScreen'))

// Pages outside the app shell: sign-in, check-in, the public pages, and a dashboard on a big screen.
export const routes: AppRoute[] = [
  { path: '/login', element: createElement(Login), shell: false },
  { path: '/checkin', element: createElement(Checkin), shell: false },
  { path: '/status', element: createElement(PublicStatus), shell: false },
  { path: '/help/:seat', element: createElement(SeatHelp), shell: false },
  { path: '/dashboards/:id', element: createElement(DashboardScreen), shell: false },
]
