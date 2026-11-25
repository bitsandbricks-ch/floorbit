import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Services = lazy(() => import('@/pages/Services'))
const ViewPage = lazy(() => import('@/pages/monitoring/ViewPage'))

export const routes: AppRoute[] = [
  { path: '/services', element: createElement(Services) },
  { path: '/dns', element: createElement(ViewPage, { key: 'dns', view: 'dns' }) },
  { path: '/lancache', element: createElement(ViewPage, { key: 'lancache', view: 'lancache' }) },
]
