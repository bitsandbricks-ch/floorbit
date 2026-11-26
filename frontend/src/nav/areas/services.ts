import { IconHeartbeat, IconServer, IconServerBolt, IconWorldWww } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Services, with DNS and the LAN cache as tabs.
export const area: NavArea = {
  hub: 'services',
  tabs: ['dns', 'lancache'],
  icons: {
    services: IconServerBolt,
    dns: IconWorldWww,
    lancache: IconServer,
    health: IconHeartbeat,
  },
}
