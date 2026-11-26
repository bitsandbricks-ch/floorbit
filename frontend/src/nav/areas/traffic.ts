import { IconApps, IconChartPie, IconDeviceGamepad2, IconGauge, IconListSearch, IconWorldWww } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Traffic: what the hall does. Its overview, games and downloads, DNS, applications, speed tests
// and the flow lookup as tabs (#1642).
export const area: NavArea = {
  hub: 'traffic',
  tabs: ['games', 'dns', 'applications', 'speedtests', 'flowLookup'],
  icons: {
    traffic: IconChartPie,
    games: IconDeviceGamepad2,
    dns: IconWorldWww,
    applications: IconApps,
    flowLookup: IconListSearch,
    speedtests: IconGauge,
  },
}
