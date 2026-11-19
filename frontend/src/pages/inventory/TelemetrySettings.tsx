import { Alert, Anchor, Button, Chip, Collapse, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { Origin } from '@/api/types'
import { EntitySelect, type EntityOption } from '@/components/EntitySelect'
import { FromLabel } from './ScopeEditors'
import type { DeviceTelemetryInfo } from './telemetry'

const DRIVERS = ['snmp', 'traps', 'nxapi', 'restconf', 'opnsense', 'gnmi', 'mdt', 'push'] as const
const FDB = ['qbridge', 'cisco_vlans', 'bridge', 'off'] as const
// Every property this form owns (floorbit/telemetry/targets.py reads them); the rest stay untouched.
const KEYS = ['telemetry_drivers', 'telemetry_fdb', 'telemetry_vlans', 'telemetry_mdt_node', 'telemetry_address', 'telemetry_agent',
  'telemetry_port_snmp', 'telemetry_port_gnmi', 'telemetry_port_api', 'telemetry_url', 'telemetry_verify_tls'] as const
type Key = typeof KEYS[number]
const PORTS: [Key, string][] = [['telemetry_port_snmp', '161'], ['telemetry_port_gnmi', '50051 / 9339'], ['telemetry_port_api', '443']]
type Collect = 'inherit' | 'on' | 'off'

const words = (v: string | undefined) => (v ?? '').split(/[,\s]+/).filter(Boolean)

/** Telemetry for a device, a group, a tag or all devices: on or off, how it is collected, and
 *  where. Empty fields take what the group above says, or what the device's software suggests. */
export function TelemetrySettings({ own, ownFeatures, inherited, resolvedOn, info, canEdit, busy, onSave }: {
  own: Record<string, string>
  ownFeatures: Record<string, boolean>
  /** A device's resolved properties; a group has none (it is where they come from). */
  inherited?: Record<string, { value: string; from: Origin }>
  /** Whether the feature is on for a device, and who says so. */
  resolvedOn?: { on: boolean; from: Origin | null }
  info?: DeviceTelemetryInfo
  canEdit: boolean; busy: boolean
  onSave: (body: { properties: Record<string, string>; features: Record<string, boolean | null> }) => void
}) {
  const { t } = useTranslation()
  const isDevice = !!inherited
  const start = () => Object.fromEntries(KEYS.map((k) => [k, own[k] ?? ''])) as Record<Key, string>
  const startCollect = (): Collect => ('telemetry' in ownFeatures ? (ownFeatures.telemetry ? 'on' : 'off') : 'inherit')
  const [form, setForm] = useState(start)
  const [collect, setCollect] = useState<Collect>(startCollect)
  const [more, setMore] = useState(!!(own.telemetry_url || own.telemetry_verify_tls))
  const set = (k: Key, v: string) => setForm((f) => ({ ...f, [k]: v }))
  const dirty = collect !== startCollect() || KEYS.some((k) => form[k] !== (own[k] ?? ''))
  // What applies when the field here is empty: a group's or a tag's value, never the device's own.
  const above = (k: Key) => (inherited?.[k] && inherited[k].from.type !== 'device' ? inherited[k] : null)
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') })
  const agentName = (id: string) => agents.data?.options.find((o) => o.value === id)?.label ?? id
  const driverName = (d: string) => t(`telemetry.driver.${d}`, { defaultValue: d })
  const fdbName = (f: string) => t(`inventory.telemetry.fdb.${f}`, { defaultValue: f })
  const list = (ds: string[]) => (ds.length ? ds.map(driverName).join(', ') : t('inventory.telemetry.nothing'))

  // How: the drivers set here, else above, else the automatic ones.
  const picked = words(form.telemetry_drivers)
  const choosing = !!form.telemetry_drivers
  const effective = choosing ? picked : above('telemetry_drivers') ? words(above('telemetry_drivers')!.value)
    : info?.target?.drivers ?? info?.auto.drivers ?? []
  const fdbNow = form.telemetry_fdb || above('telemetry_fdb')?.value || info?.auto.fdb || ''
  const needsLogin = isDevice && info && ((effective.includes('snmp') && !info.logins.snmp)
    || (effective.some((d) => ['nxapi', 'restconf', 'opnsense'].includes(d)) && !info.logins.api))

  const save = () => {
    const properties = { ...own }
    for (const k of KEYS) {
      if (form[k].trim()) properties[k] = form[k].trim()
      else delete properties[k]
    }
    onSave({ properties, features: { ...ownFeatures, telemetry: collect === 'inherit' ? null : collect === 'on' } })
  }

  const nowOn = isDevice ? (collect === 'inherit' ? !!resolvedOn && (resolvedOn.from?.type === 'device' ? false : resolvedOn.on) : collect === 'on') : collect !== 'off'
  const disabled = !canEdit || busy

  return (
    <Stack gap="lg">
      <Row label={t('inventory.telemetry.collect')} hint={collect === 'inherit' && resolvedOn && resolvedOn.from?.type !== 'device'
        ? <>{resolvedOn.on ? t('inventory.features.isOn') : t('inventory.features.isOff')} · <FromLabel from={resolvedOn.from} /></>
        : collect === 'inherit' ? t('inventory.telemetry.collectInherit') : null}>
        <SegmentedControl size="sm" disabled={disabled} value={collect} onChange={(v) => setCollect(v as Collect)}
          aria-label={t('inventory.telemetry.collect')}
          data={[{ value: 'inherit', label: t('inventory.features.inherit') }, { value: 'on', label: t('inventory.features.on') },
            { value: 'off', label: t('inventory.features.off') }]} />
      </Row>

      {nowOn && (
        <>
          <Stack gap="xs">
            <Group justify="space-between" wrap="wrap" gap="xs">
              <Text size="sm" fw={600}>{t('inventory.telemetry.methods')}</Text>
              <SegmentedControl size="xs" disabled={disabled} value={choosing ? 'pick' : 'auto'}
                aria-label={t('inventory.telemetry.methods')}
                data={[{ value: 'auto', label: above('telemetry_drivers') ? t('inventory.features.inherit') : t('inventory.telemetry.auto') },
                  { value: 'pick', label: t('inventory.telemetry.pick') }]}
                onChange={(v) => set('telemetry_drivers', v === 'pick' ? (effective.length ? effective : ['snmp', 'traps']).join(' ') : '')} />
            </Group>
            {choosing ? (
              <Chip.Group multiple value={picked} onChange={(v) => set('telemetry_drivers', DRIVERS.filter((d) => v.includes(d)).join(' '))}>
                <Group gap={6}>
                  {DRIVERS.map((d) => <Chip key={d} value={d} size="sm" disabled={disabled}>{driverName(d)}</Chip>)}
                </Group>
              </Chip.Group>
            ) : (
              <Text size="sm">
                {above('telemetry_drivers') ? <>{list(effective)} · <FromLabel from={above('telemetry_drivers')!.from} /></>
                  : info ? t('inventory.telemetry.autoDevice', { list: list(info.auto.drivers), platform: t(`telemetry.platform.${info.platform}`, { defaultValue: info.platform }) })
                    : t('inventory.telemetry.autoGroup')}
              </Text>
            )}
            <Text size="xs" c="dimmed">{t('inventory.telemetry.methodsHint')}</Text>
            {needsLogin && <Alert color="warn" py={6}>{t('inventory.telemetry.needsLogin')}</Alert>}
          </Stack>

          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            <div>
              <Select label={t('inventory.telemetry.fdbLabel')} disabled={disabled} allowDeselect={false}
                value={form.telemetry_fdb} onChange={(v) => set('telemetry_fdb', v ?? '')}
                data={[{ value: '', label: above('telemetry_fdb') ? t('inventory.telemetry.asAbove', { value: fdbName(above('telemetry_fdb')!.value) })
                  : info ? t('inventory.telemetry.autoValue', { value: fdbName(info.auto.fdb) }) : t('inventory.telemetry.autoFdb') },
                ...FDB.map((f) => ({ value: f, label: fdbName(f) }))]} />
              {above('telemetry_fdb') && !form.telemetry_fdb && <FromLabel from={above('telemetry_fdb')!.from} />}
            </div>
            {(!isDevice || fdbNow === 'cisco_vlans') && (
              <Inherited from={!form.telemetry_vlans ? above('telemetry_vlans')?.from : null}>
                <TextInput label={t('inventory.telemetry.vlans')} disabled={disabled} value={form.telemetry_vlans}
                  placeholder={above('telemetry_vlans')?.value ?? (info ? (info.auto.vlans.join(' ') || t('inventory.telemetry.noVlans')) : t('inventory.telemetry.vlansAuto'))}
                  description={t('inventory.telemetry.vlansHint')} inputWrapperOrder={['label', 'input', 'description']}
                  onChange={(e) => set('telemetry_vlans', e.currentTarget.value.replace(/[^\d,\s]/g, ''))} />
              </Inherited>
            )}
            {(!isDevice || effective.includes('mdt')) && (
              <Inherited from={!form.telemetry_mdt_node ? above('telemetry_mdt_node')?.from : null}>
                <TextInput label={t('inventory.telemetry.mdtNode')} disabled={disabled} value={form.telemetry_mdt_node}
                  placeholder={above('telemetry_mdt_node')?.value ?? info?.auto.mdt_node ?? t('inventory.telemetry.mdtAuto')}
                  onChange={(e) => set('telemetry_mdt_node', e.currentTarget.value)} />
              </Inherited>
            )}
          </SimpleGrid>

          <Stack gap="sm">
            <Text size="sm" fw={600}>{t('inventory.telemetry.where')}</Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              <Inherited from={!form.telemetry_agent ? above('telemetry_agent')?.from : null}>
                <EntitySelect kind="agents" label={t('inventory.telemetry.agent')} clearable disabled={disabled}
                  description={t('inventory.telemetry.agentHint')} inputWrapperOrder={['label', 'input', 'description']}
                  placeholder={above('telemetry_agent') ? agentName(above('telemetry_agent')!.value) : t('inventory.telemetry.anyAgent')}
                  value={form.telemetry_agent} onChange={(v) => set('telemetry_agent', v ?? '')} />
              </Inherited>
              <Inherited from={!form.telemetry_address ? above('telemetry_address')?.from : null}>
                <TextInput label={t('inventory.telemetry.address')} disabled={disabled} value={form.telemetry_address}
                  placeholder={above('telemetry_address')?.value ?? info?.auto.address ?? t('inventory.telemetry.addressAuto')}
                  description={t('inventory.telemetry.addressHint')} inputWrapperOrder={['label', 'input', 'description']}
                  onChange={(e) => set('telemetry_address', e.currentTarget.value.trim())} />
              </Inherited>
            </SimpleGrid>
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
              {PORTS.map(([k, usual]) => (
                <Inherited key={k} from={!form[k] ? above(k)?.from : null}>
                  <TextInput label={t(`inventory.telemetry.${k}`)} inputMode="numeric" disabled={disabled}
                    placeholder={above(k)?.value ?? usual} value={form[k]}
                    onChange={(e) => set(k, e.currentTarget.value.replace(/\D/g, '').slice(0, 5))} />
                </Inherited>
              ))}
            </SimpleGrid>
            <Text size="xs" c="dimmed">{t('inventory.telemetry.portsHint')}</Text>
          </Stack>

          <div>
            <Anchor component="button" type="button" size="sm" onClick={() => setMore((m) => !m)} aria-expanded={more}>
              {more ? t('inventory.telemetry.less') : t('inventory.telemetry.more')}
            </Anchor>
            <Collapse expanded={more}>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mt="sm">
                <Inherited from={!form.telemetry_url ? above('telemetry_url')?.from : null}>
                  <TextInput label={t('inventory.telemetry.url')} disabled={disabled} value={form.telemetry_url}
                    placeholder={above('telemetry_url')?.value ?? 'https://198.51.100.10'}
                    description={t('inventory.telemetry.urlHint')} inputWrapperOrder={['label', 'input', 'description']}
                    onChange={(e) => set('telemetry_url', e.currentTarget.value.trim())} />
                </Inherited>
                <Select label={t('inventory.telemetry.verifyTls')} disabled={disabled} allowDeselect={false}
                  value={form.telemetry_verify_tls} onChange={(v) => set('telemetry_verify_tls', v ?? '')}
                  data={[{ value: '', label: t('inventory.telemetry.verifyDefault') }, { value: 'true', label: t('inventory.telemetry.verifyYes') },
                    { value: 'false', label: t('inventory.telemetry.verifyNo') }]} />
              </SimpleGrid>
            </Collapse>
          </div>
        </>
      )}

      {canEdit && (
        <Group justify="flex-end">
          <Button disabled={!dirty} loading={busy} onClick={save}>{t('inventory.save')}</Button>
        </Group>
      )}
    </Stack>
  )
}

function Row({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <Group justify="space-between" wrap="wrap" gap="xs" align="center">
      <Stack gap={2}>
        <Text size="sm" fw={600}>{label}</Text>
        {hint && <Text size="xs" c="dimmed">{hint}</Text>}
      </Stack>
      {children}
    </Group>
  )
}

function Inherited({ from, children }: { from: Origin | null | undefined; children: ReactNode }) {
  return <div>{children}{from && <FromLabel from={from} />}</div>
}
