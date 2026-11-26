import { IconChecklist, IconFileText, IconHierarchy2, IconLayoutGrid, IconListCheck, IconMap, IconShield } from '@tabler/icons-react'
import type { NavArea } from '../sections'

// Pages that are a row of their own, with no tabs (the start pages, Logs), or that the sidebar
// doesn't list (Set up, the checks before doors open, the topology view): only their icons.
export const area: NavArea = {
  icons: {
    overview: IconLayoutGrid,
    floorPlan: IconMap,
    topology: IconHierarchy2,
    logs: IconFileText,
    security: IconShield,
    preflight: IconChecklist,
    setup: IconListCheck,
  },
}
