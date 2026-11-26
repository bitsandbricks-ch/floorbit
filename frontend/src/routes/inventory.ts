import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Inventory = lazy(() => import('@/pages/Inventory'))
const DevicePage = lazy(() => import('@/pages/inventory/DevicePage'))
const NewDevicePage = lazy(() => import('@/pages/inventory/NewDevicePage'))
const ScopePage = lazy(() => import('@/pages/inventory/ScopePage'))
const EntryPage = lazy(() => import('@/pages/inventory/EntryPage'))
const PropertiesPage = lazy(() => import('@/pages/inventory/PropertiesPage'))
const ReadsPage = lazy(() => import('@/pages/inventory/ReadsPage'))

export const routes: AppRoute[] = [
  { path: '/inventory', element: createElement(Inventory) },
  { path: '/inventory/devices/new', element: createElement(NewDevicePage) },
  { path: '/inventory/devices/:id', element: createElement(DevicePage) },
  { path: '/inventory/groups/:id', element: createElement(ScopePage, { kind: 'group' }) },
  { path: '/inventory/tags/:id', element: createElement(ScopePage, { kind: 'tag' }) },
  { path: '/inventory/defaults', element: createElement(ScopePage, { kind: 'defaults' }) },
  { path: '/inventory/entries/:type/:id', element: createElement(EntryPage) },
  { path: '/inventory/properties', element: createElement(PropertiesPage) },
  { path: '/inventory/reads/:role', element: createElement(ReadsPage) },
]
