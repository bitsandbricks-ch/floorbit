import { IconApps, IconChartLine, IconChartPie, IconDeviceGamepad2, IconGauge, IconListSearch } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Traffic: games, applications, the flow lookup, figures and speed tests as tabs.
export const area: NavArea = {
  hub: 'traffic',
  tabs: ['games', 'applications', 'flowLookup', 'stats', 'speedtests'],
  icons: {
    traffic: IconChartPie,
    games: IconDeviceGamepad2,
    applications: IconApps,
    flowLookup: IconListSearch,
    stats: IconChartLine,
    speedtests: IconGauge,
  },
}
