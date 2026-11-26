import { IconHierarchy2, IconNetwork, IconWall, IconWifi } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Network: switches, firewalls and Wi-Fi as tabs of one row.
export const area: NavArea = {
  hub: 'network',
  tabs: ['switches', 'firewalls', 'wifi'],
  icons: {
    network: IconNetwork,
    switches: IconHierarchy2,
    firewalls: IconWall,
    wifi: IconWifi,
  },
}
