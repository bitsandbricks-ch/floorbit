import { Button, Group, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { EntitySelect, type EntityOption } from '@/components/EntitySelect'
import type { Origin } from '@/api/types'
import { FromLabel } from './ScopeEditors'

/** The properties telemetry reads (floorbit/telemetry/targets.py): which agent collects, and a port
 *  per way of asking. Like every property, a group, tag or type can set them for its devices. */
const TELEMETRY_KEYS = ['telemetry_agent', 'telemetry_port_snmp', 'telemetry_port_gnmi', 'telemetry_port_api'] as const
type Key = typeof TELEMETRY_KEYS[number]
const PORTS: [Key, string][] = [['telemetry_port_snmp', '161'], ['telemetry_port_gnmi', '50051 / 9339'], ['telemetry_port_api', '443']]

/** Agent and ports for a device or a group: empty takes what the group above says, or the usual. */
export function TelemetryFields({ own, inherited, canEdit, busy, onSave }: {
  own: Record<string, string>
  /** The device's resolved properties; a group has none (it is where they come from). */
  inherited?: Record<string, { value: string; from: Origin }>
  canEdit: boolean; busy: boolean
  onSave: (properties: Record<string, string>) => void
}) {
  const { t } = useTranslation()
  const start = () => Object.fromEntries(TELEMETRY_KEYS.map((k) => [k, own[k] ?? ''])) as Record<Key, string>
  const [form, setForm] = useState(start)
  const dirty = TELEMETRY_KEYS.some((k) => form[k] !== (own[k] ?? ''))
  // What applies when the field here is empty: a group's or a tag's value, never the device's own.
  const above = (k: Key) => (inherited?.[k] && inherited[k].from.type !== 'device' ? inherited[k] : null)
  // The same list the agent field shows (cached): an inherited agent by its name, not its id.
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') })
  const agentName = (id: string) => agents.data?.options.find((o) => o.value === id)?.label ?? id
  const save = () => {
    const next = { ...own }
    for (const k of TELEMETRY_KEYS) {
      if (form[k].trim()) next[k] = form[k].trim()
      else delete next[k]
    }
    onSave(next)
  }
  return (
    <Stack gap="sm">
      <div>
        <EntitySelect kind="agents" label={t('inventory.telemetry.agent')} clearable disabled={!canEdit}
          description={t('inventory.telemetry.agentHint')} inputWrapperOrder={['label', 'input', 'description']}
          placeholder={above('telemetry_agent') ? agentName(above('telemetry_agent')!.value) : t('inventory.telemetry.anyAgent')}
          value={form.telemetry_agent} onChange={(v) => setForm((f) => ({ ...f, telemetry_agent: v ?? '' }))} />
        {above('telemetry_agent') && !form.telemetry_agent && <FromLabel from={above('telemetry_agent')!.from} />}
      </div>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        {PORTS.map(([k, usual]) => (
          <div key={k}>
            <TextInput label={t(`inventory.telemetry.${k}`)} inputMode="numeric" disabled={!canEdit}
              placeholder={above(k)?.value ?? usual} value={form[k]}
              onChange={(e) => { const v = e.currentTarget.value.replace(/\D/g, '').slice(0, 5); setForm((f) => ({ ...f, [k]: v })) }} />
            {above(k) && !form[k] && <FromLabel from={above(k)!.from} />}
          </div>
        ))}
      </SimpleGrid>
      <Text size="xs" c="dimmed">{t('inventory.telemetry.portsHint')}</Text>
      {canEdit && (
        <Group justify="flex-end">
          <Button size="xs" disabled={!dirty} loading={busy} onClick={save}>{t('inventory.save')}</Button>
        </Group>
      )}
    </Stack>
  )
}
