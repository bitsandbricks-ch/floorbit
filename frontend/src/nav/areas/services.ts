import { IconHeartbeat, IconServerBolt } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Services: one page that says whether each service works (#1642). What the hall looks up and
// downloads is under Traffic.
export const area: NavArea = {
  icons: {
    services: IconServerBolt,
    health: IconHeartbeat,
  },
}
