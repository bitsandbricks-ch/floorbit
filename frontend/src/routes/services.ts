import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Services = lazy(() => import('@/pages/Services'))

export const routes: AppRoute[] = [
  { path: '/services', element: createElement(Services) },
]
