import { Group, Select, Text, TextInput, type SelectProps } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'

export type EntityKind = 'devices' | 'switches' | 'ports' | 'seats' | 'blocks' | 'halls' | 'firewalls' | 'agents' | 'users' | 'teams' | 'panels' | 'panel-ports' | 'dashboards' | 'pages'
export interface EntityOption { value: string; label: string; group?: string; hint?: string; used?: string | null }

type Props = Omit<SelectProps, 'data' | 'value' | 'onChange'> & {
  kind: EntityKind
  value: string | null | undefined
  onChange: (value: string) => void
  /** Ports: the switch whose ports to list. */
  switchName?: string
  /** Panel ports: the patch panel whose ports to list. */
  panelName?: string
  /** Ports: also list the ones a cable already holds (marked with who holds them). */
  showUsed?: boolean
}

/** Every field that names something Floorbit knows (a switch, a port, a seat, a block, a team...)
 *  picks it from the real list (GET /api/options/<kind>, floorbit/blueprints/options.py), never
 *  free text. Ports list only free ones unless asked; the current value always stays listed. */
export function EntitySelect({ kind, value, onChange, switchName, panelName, showUsed = false, ...rest }: Props) {
  const { t } = useTranslation()
  // Ports belong to a switch, panel ports to a patch panel: nothing to list until that is picked.
  const parent = kind === 'ports' ? { key: 'switch', name: switchName } : kind === 'panel-ports' ? { key: 'panel', name: panelName } : null
  const needsSwitch = !!parent
  const query = useQuery({
    queryKey: qk.options(kind, parent?.name ?? ''),
    queryFn: () => get<{ options: EntityOption[] }>(`/api/options/${kind}${parent ? `?${parent.key}=${encodeURIComponent(parent.name ?? '')}` : ''}`),
    enabled: !parent || Boolean(parent.name),
    staleTime: 30_000,
  })
  const all = query.data?.options ?? []
  // A switch the monitoring source can't list ports for (or a panel without its port count): say so
  // and let the crew type the port.
  if (parent?.name && query.isSuccess && all.length === 0) {
    return (
      // The one place a port is typed: the source lists none.
      <TextInput label={rest.label} required={rest.required} error={rest.error} placeholder={kind === 'ports' ? 'Gi1/0/1' : '1'}
        description={t(kind === 'ports' ? 'ui.noPortList' : 'ui.noPanelPorts')} value={value ?? ''} onChange={(e) => onChange(e.currentTarget.value)} />
    )
  }
  const shown = all.filter((o) => showUsed || !o.used || o.value === value)
  const byValue = new Map(shown.map((o) => [o.value, o]))
  const groups = [...new Set(shown.map((o) => o.group ?? ''))]
  const data = groups.length > 1
    ? groups.map((g) => ({ group: g ? t(`ui.group.${g}`, { defaultValue: g }) : t('ui.group.other'), items: shown.filter((o) => (o.group ?? '') === g).map(({ value: v, label }) => ({ value: v, label })) }))
    : shown.map(({ value: v, label }) => ({ value: v, label }))
  return (
    <Select searchable clearable={!rest.required} allowDeselect={false} data={data} value={value || null}
      onChange={(v) => onChange(v ?? '')}
      disabled={rest.disabled || (needsSwitch && !parent?.name)}
      placeholder={needsSwitch && !parent?.name ? t(kind === 'ports' ? 'ui.pickSwitchFirst' : 'ui.pickPanelFirst') : (rest.placeholder ?? t('ui.pickFromList'))}
      nothingFoundMessage={query.isPending ? t('common.loading') : t('ui.nothingFound')}
      renderOption={({ option, checked }) => {
        const o = byValue.get(option.value)
        return (
          <Group gap="xs" justify="space-between" wrap="nowrap" w="100%">
            <Text size="sm" fw={checked ? 600 : undefined} truncate>{option.label}</Text>
            {(o?.used || o?.hint) && <Text size="xs" c="dimmed" truncate>{o.used ? t('ui.usedBy', { who: o.used }) : o.hint}</Text>}
          </Group>
        )
      }}
      {...rest} />
  )
}
