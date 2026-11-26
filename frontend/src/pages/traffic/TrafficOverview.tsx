import { Stack } from '@mantine/core'
import type { ViewProps } from '@/pages/monitoring/pages'
import StatsView from '../stats/StatsView'
import TrafficView from './TrafficView'

/** Traffic's first tab: how much the hall moves (bandwidth now and at its peak, uplinks, the
 *  busiest seats) and what it is made of (the flows). Stats was its own tab before (#1642). */
export default function TrafficOverview({ expanded }: ViewProps) {
  return (
    <Stack gap="lg">
      <section><StatsView expanded={expanded} /></section>
      <section><TrafficView expanded={expanded} /></section>
    </Stack>
  )
}
