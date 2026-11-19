import type { StatusState } from '@/api/types'

/** The status page's state as a Mantine colour. */
export const COLOR: Record<StatusState, string> = {
  operational: 'up', degraded: 'warn', outage: 'down', maintenance: 'warn', unknown: 'gray',
}
