import { IconLayoutCards, IconLayoutDashboard } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Dashboards, with the widget library as a tab.
export const area: NavArea = {
  hub: 'dashboards',
  tabs: ['widgets'],
  icons: {
    dashboards: IconLayoutDashboard,
    widgets: IconLayoutCards,
  },
}
