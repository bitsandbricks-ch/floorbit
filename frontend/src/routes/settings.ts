import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Setup = lazy(() => import('@/pages/Setup'))
const Settings = lazy(() => import('@/pages/Settings'))
const Agents = lazy(() => import('@/pages/Agents'))
const AgentDetail = lazy(() => import('@/pages/AgentDetail'))
const AgentGroup = lazy(() => import('@/pages/AgentGroup'))

export const routes: AppRoute[] = [
  { path: '/setup', element: createElement(Setup) },
  { path: '/settings/:section?', element: createElement(Settings) },
  { path: '/settings/agents', element: createElement(Agents) },
  { path: '/settings/agents/:id', element: createElement(AgentDetail) },
  { path: '/settings/agents/groups/:gid', element: createElement(AgentGroup) },
]
