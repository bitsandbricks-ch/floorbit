import { IconApps, IconChartLine, IconChartPie, IconDeviceGamepad2, IconGauge } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Traffic: games, applications, figures and speed tests as tabs.
export const area: NavArea = {
  hub: 'traffic',
  tabs: ['games', 'applications', 'stats', 'speedtests'],
  icons: {
    traffic: IconChartPie,
    games: IconDeviceGamepad2,
    applications: IconApps,
    stats: IconChartLine,
    speedtests: IconGauge,
  },
}
