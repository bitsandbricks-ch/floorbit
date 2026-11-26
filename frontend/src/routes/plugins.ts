import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Plugins = lazy(() => import('@/pages/Plugins'))
const PluginSettings = lazy(() => import('@/pages/PluginSettings'))
const PluginPage = lazy(() => import('@/pages/PluginPage'))

export const routes: AppRoute[] = [
  { path: '/settings/plugins', element: createElement(Plugins) },
  { path: '/settings/plugins/:id', element: createElement(PluginSettings) },
  { path: '/plugins/:plugin/:page', element: createElement(PluginPage) },
]
