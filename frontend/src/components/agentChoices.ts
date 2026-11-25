import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { EntityOption } from '@/components/EntitySelect'
import { useInventoryGroups } from '@/pages/inventory/scope'

/** The choices for "Collected by" (telemetry, issue #869) and "Checked from" (service checks,
 *  #1444): the agents with a tag (``tag:<id>``) or one agent; empty is any agent. ``name`` says a
 *  value in words. */
export function useAgentChoices() {
  const { t } = useTranslation()
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') })
  const tags = useInventoryGroups().data?.tags ?? []
  const name = (v: string) => (v.startsWith('tag:')
    ? t('inventory.telemetry.byTag', { tag: tags.find((x) => x.id === v.slice(4))?.name ?? v.slice(4) })
    : agents.data?.options.find((o) => o.value === v)?.label ?? v)
  const data = [
    ...(tags.length ? [{ group: t('inventory.telemetry.tagsGroup'),
      items: tags.map((x) => ({ value: `tag:${x.id}`, label: t('inventory.telemetry.byTag', { tag: x.name }) })) }] : []),
    { group: t('inventory.telemetry.agentsGroup'), items: (agents.data?.options ?? []).map((o) => ({ value: o.value, label: o.label })) },
  ]
  return { data, name }
}
