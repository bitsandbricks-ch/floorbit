import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { Device } from '@/api/types'
import type { EntityOption } from '@/components/EntitySelect'
import { useInventoryGroups } from './scope'

/** Sorting and words for the inventory list's Uplink, Last 24 h and Agent columns (issue #981). */

/** A port speed as switches say it: 100M, 1G, 2.5G, 10G. */
export function linkSpeed(b: number): string {
  return b >= 1e9 ? `${+(b / 1e9).toFixed(1)}G` : `${Math.round(b / 1e6)}M`
}

/** Sort key: down first, then slower than planned, then by speed. */
export const uplinkSort = (d: Device) => (!d.uplink ? -1 : d.uplink.state === 'down' ? 0 : d.uplink.issue === 'slow' ? 1 : 2 + (d.uplink.speed_bps ?? 0) / 1e12)

/** Sort key: the most time down first when sorted down. */
export const lastDaySort = (d: Device) => (d.last_day ? d.last_day.reduce((a, b) => a + b, 0) : -1)

/** Who reads the device: Auto, the agents with a tag, or one agent (telemetry.agent). */
export function useAgentName() {
  const { t } = useTranslation()
  const tags = useInventoryGroups().data?.tags ?? []
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') })
  return (v: string | undefined) => (!v ? t('inventory.agentAuto')
    : v.startsWith('tag:') ? t('inventory.telemetry.byTag', { tag: tags.find((x) => x.id === v.slice(4))?.name ?? v.slice(4) })
      : agents.data?.options.find((o) => o.value === v)?.label ?? v)
}
