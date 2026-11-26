import { IconAlertCircle, IconAlertTriangle, IconArrowsExchange, IconBroadcast, IconClipboardCheck, IconLifebuoy } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Helpdesk: a row that only bundles the crew's work as tabs.
export const area: NavArea = {
  hub: 'helpdesk',
  tabs: ['problems', 'incidents', 'handover', 'networkStatus'],
  icons: {
    helpdesk: IconLifebuoy,
    problems: IconAlertTriangle,
    incidents: IconAlertCircle,
    handover: IconArrowsExchange,
    networkStatus: IconBroadcast,
    jobs: IconClipboardCheck,
  },
}
