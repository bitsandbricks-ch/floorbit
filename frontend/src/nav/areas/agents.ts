import { IconActivityHeartbeat, IconPlugConnected } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Local agents, with the telemetry collector as a tab.
export const area: NavArea = {
  hub: 'agents',
  tabs: ['telemetry'],
  icons: {
    agents: IconPlugConnected,
    telemetry: IconActivityHeartbeat,
  },
}
