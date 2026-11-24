import { useTranslation } from 'react-i18next'
import { useInventory } from '@/api/queries'
import { useInventoryGroups } from '@/pages/inventory/scope'

/** A range's own page: its inventory entry, where it is changed (#1312). */
export const rangePage = (id: string) => `/inventory/entries/firewall-range/${encodeURIComponent(id)}`

export const ROUTE_TONE = { primary: 'up', failover: 'warn', unknown: 'gray', down: 'down' } as const

export interface SwitchScope {
  names: Map<string, string>
  options: { group: string; items: { value: string; label: string }[] }[]
}

/** What a range can be for (issue #1062): the inventory's switch groups (a colour, a switch type) and switches. */
export function useSwitchScope(): SwitchScope {
  const { t } = useTranslation()
  const groups = useInventoryGroups().data?.groups ?? []
  const switches = (useInventory(false).data?.devices ?? []).filter((d) => d.role === 'switch')
  const names = new Map<string, string>([...groups.map((g) => [g.id, g.name] as const), ...switches.map((d) => [d.id, d.name] as const)])
  const options = [
    { group: t('firewalls.switchGroups'), items: groups.map((g) => ({ value: g.id, label: g.name })) },
    { group: t('firewalls.switchList'), items: switches.map((d) => ({ value: d.id, label: d.name })) },
  ].filter((o) => o.items.length > 0)
  return { names, options }
}

