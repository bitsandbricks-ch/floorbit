import { createElement, lazy } from 'react'
import type { AppRoute } from '@/lib/appRoute'

const Logs = lazy(() => import('@/pages/Logs'))
const Commands = lazy(() => import('@/pages/Commands'))
const TerminalPage = lazy(() => import('@/pages/Terminal'))
const Configs = lazy(() => import('@/pages/Configs'))

export const routes: AppRoute[] = [
  { path: '/logs', element: createElement(Logs) },
  { path: '/commands', element: createElement(Commands) },
  { path: '/terminal', element: createElement(TerminalPage) },
  { path: '/configs', element: createElement(Configs) },
]
