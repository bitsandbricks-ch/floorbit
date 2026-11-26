import { IconBolt, IconPlug, IconServer } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Inventory, with cables and power as tabs.
export const area: NavArea = {
  hub: 'inventory',
  tabs: ['cables', 'power'],
  icons: {
    inventory: IconServer,
    cables: IconPlug,
    power: IconBolt,
  },
}
