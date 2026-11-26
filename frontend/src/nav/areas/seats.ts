import { IconArmchair, IconDeviceDesktopSearch, IconHierarchy2, IconTableOptions, IconUserCheck, IconWalk } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Seats: mapping, check-in, the walk-through, switch areas and endpoints as tabs.
export const area: NavArea = {
  hub: 'seats',
  tabs: ['seatMapping', 'checkins', 'seatWalk', 'switchAreas', 'endpoints'],
  icons: {
    seats: IconArmchair,
    seatMapping: IconTableOptions,
    checkins: IconUserCheck,
    seatWalk: IconWalk,
    switchAreas: IconHierarchy2,
    endpoints: IconDeviceDesktopSearch,
  },
}
