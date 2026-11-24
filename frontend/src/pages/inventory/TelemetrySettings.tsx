import { Alert, Anchor, Chip, Collapse, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useLeaveWarning } from '@/components/useLeaveWarning'
import { SaveBar } from '@/pages/settings/editor'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { Origin } from '@/api/types'
import { EntitySelect, type EntityOption } from '@/components/EntitySelect'
import { FromLabel } from './ScopeEditors'
import type { DeviceTelemetryInfo } from './telemetry'

const DRIVERS = ['snmp', 'traps', 'nxapi', 'restconf', 'opnsense', 'gnmi', 'mdt', 'push'] as const
const FDB = ['qbridge', 'cisco_vlans', 'bridge', 'off'] as const
// Every property this form owns, by the form's own short name (floorbit/telemetry/targets.py reads
// them; docs/telemetry.md lists them); the rest stay untouched.
const PROP = {
  drivers: 'telemetry.drivers', fdb: 'telemetry.snmp.fdb', vlans: 'telemetry.snmp.vlans', mdt_node: 'telemetry.mdt.node',
  address: 'telemetry.address', agent: 'telemetry.agent', port_snmp: 'telemetry.snmp.port', port_gnmi: 'telemetry.gnmi.port',
  port_api: 'telemetry.api.port', url: 'telemetry.api.url', verify_tls: 'telemetry.verify_tls',
} as const
type Key = keyof typeof PROP
const KEYS = Object.keys(PROP) as Key[]
const PORTS: [Key, string][] = [['port_snmp', '161'], ['port_gnmi', '50051 / 9339'], ['port_api', '443']]
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
  const start = () => Object.fromEntries(KEYS.map((k) => [k, own[PROP[k]] ?? ''])) as Record<Key, string>
  const startCollect = (): Collect => ('telemetry' in ownFeatures ? (ownFeatures.telemetry ? 'on' : 'off') : 'inherit')
  const [form, setForm] = useState(start)
  const [collect, setCollect] = useState<Collect>(startCollect)
  const [more, setMore] = useState(!!(own[PROP.url] || own[PROP.verify_tls]))
  const set = (k: Key, v: string) => setForm((f) => ({ ...f, [k]: v }))
  const count = (collect !== startCollect() ? 1 : 0) + KEYS.filter((k) => form[k].trim() !== (own[PROP[k]] ?? '')).length
  useLeaveWarning(count > 0)
  // What applies when the field here is empty: a group's or a tag's value, never the device's own.
  const above = (k: Key) => {
    const v = inherited?.[PROP[k]]
    return v && v.from.type !== 'device' ? v : null
  }
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') })
  const agentName = (id: string) => agents.data?.options.find((o) => o.value === id)?.label ?? id
  const driverName = (d: string) => t(`telemetry.driver.${d}`, { defaultValue: d })
  const fdbName = (f: string) => t(`inventory.telemetry.fdb.${f}`, { defaultValue: f })
  const list = (ds: string[]) => (ds.length ? ds.map(driverName).join(', ') : t('inventory.telemetry.nothing'))

  // How: the drivers set here, else above, else the automatic ones.
  const picked = words(form.drivers)
  const choosing = !!form.drivers
  const effective = choosing ? picked : above('drivers') ? words(above('drivers')!.value)
    : info?.target?.drivers ?? info?.auto.drivers ?? []
  const fdbNow = form.fdb || above('fdb')?.value || info?.auto.fdb || ''
  const needsLogin = isDevice && info && ((effective.includes('snmp') && !info.logins.snmp)
    || (effective.some((d) => ['nxapi', 'restconf', 'opnsense'].includes(d)) && !info.logins.api))

  const save = () => {
    const properties = { ...own }
    for (const k of KEYS) {
      if (form[k].trim()) properties[PROP[k]] = form[k].trim()
      else delete properties[PROP[k]]
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
                data={[{ value: 'auto', label: above('drivers') ? t('inventory.features.inherit') : t('inventory.telemetry.auto') },
                  { value: 'pick', label: t('inventory.telemetry.pick') }]}
                onChange={(v) => set('drivers', v === 'pick' ? (effective.length ? effective : ['snmp', 'traps']).join(' ') : '')} />
            </Group>
            {choosing ? (
              <Chip.Group multiple value={picked} onChange={(v) => set('drivers', DRIVERS.filter((d) => v.includes(d)).join(' '))}>
                <Group gap={6}>
                  {DRIVERS.map((d) => <Chip key={d} value={d} size="sm" disabled={disabled}>{driverName(d)}</Chip>)}
                </Group>
              </Chip.Group>
            ) : (
              <Text size="sm">
                {above('drivers') ? <>{list(effective)} · <FromLabel from={above('drivers')!.from} /></>
                  : info ? t('inventory.telemetry.autoDevice', { list: list(info.auto.drivers), platform: t(`telemetry.platform.${info.platform}`, { defaultValue: info.platform }) })
                    : t('inventory.telemetry.autoGroup')}
              </Text>
            )}
            <Text size="xs" c="dimmed">{t('inventory.telemetry.methodsHint')}</Text>
            {needsLogin && <Alert color="warn" py={6}>{t('inventory.telemetry.needsLogin')}</Alert>}
            {isDevice && info?.target && effective.includes('traps') && info.target.trap_send_port !== undefined && (
              info.target.trap_send_port === null
                ? <Alert color="warn" py={6}>{t('inventory.telemetry.trapNoPort')}</Alert>
                : <Text size="sm">{info.target.trap_user
                  ? t('inventory.telemetry.trapPortV3', { port: info.target.trap_send_port, user: info.target.trap_user })
                  : t('inventory.telemetry.trapPort', { port: info.target.trap_send_port })}</Text>
            )}
          </Stack>

          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            <div>
              <Select label={t('inventory.telemetry.fdbLabel')} disabled={disabled} allowDeselect={false}
                value={form.fdb} onChange={(v) => set('fdb', v ?? '')}
                data={[{ value: '', label: above('fdb') ? t('inventory.telemetry.asAbove', { value: fdbName(above('fdb')!.value) })
                  : info ? t('inventory.telemetry.autoValue', { value: fdbName(info.auto.fdb) }) : t('inventory.telemetry.autoFdb') },
                ...FDB.map((f) => ({ value: f, label: fdbName(f) }))]} />
              {above('fdb') && !form.fdb && <FromLabel from={above('fdb')!.from} />}
            </div>
            {(!isDevice || fdbNow === 'cisco_vlans') && (
              <Inherited from={!form.vlans ? above('vlans')?.from : null}>
                <TextInput label={t('inventory.telemetry.vlans')} disabled={disabled} value={form.vlans}
                  placeholder={above('vlans')?.value ?? (info ? (info.auto.vlans.join(' ') || t('inventory.telemetry.noVlans')) : t('inventory.telemetry.vlansAuto'))}
                  description={t('inventory.telemetry.vlansHint')} inputWrapperOrder={['label', 'input', 'description']}
                  onChange={(e) => set('vlans', e.currentTarget.value.replace(/[^\d,\s]/g, ''))} />
              </Inherited>
            )}
            {(!isDevice || effective.includes('mdt')) && (
              <Inherited from={!form.mdt_node ? above('mdt_node')?.from : null}>
                <TextInput label={t('inventory.telemetry.mdtNode')} disabled={disabled} value={form.mdt_node}
                  placeholder={above('mdt_node')?.value ?? info?.auto.mdt_node ?? t('inventory.telemetry.mdtAuto')}
                  onChange={(e) => set('mdt_node', e.currentTarget.value)} />
              </Inherited>
            )}
          </SimpleGrid>

          <Stack gap="sm">
            <Text size="sm" fw={600}>{t('inventory.telemetry.where')}</Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              <Inherited from={!form.agent ? above('agent')?.from : null}>
                <EntitySelect kind="agents" label={t('inventory.telemetry.agent')} clearable disabled={disabled}
                  description={t('inventory.telemetry.agentHint')} inputWrapperOrder={['label', 'input', 'description']}
                  placeholder={above('agent') ? agentName(above('agent')!.value) : t('inventory.telemetry.anyAgent')}
                  value={form.agent} onChange={(v) => set('agent', v ?? '')} />
              </Inherited>
              <Inherited from={!form.address ? above('address')?.from : null}>
                <TextInput label={t('inventory.telemetry.address')} disabled={disabled} value={form.address}
                  placeholder={above('address')?.value ?? info?.auto.address ?? t('inventory.telemetry.addressAuto')}
                  description={t('inventory.telemetry.addressHint')} inputWrapperOrder={['label', 'input', 'description']}
                  onChange={(e) => set('address', e.currentTarget.value.trim())} />
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
                <Inherited from={!form.url ? above('url')?.from : null}>
                  <TextInput label={t('inventory.telemetry.url')} disabled={disabled} value={form.url}
                    placeholder={above('url')?.value ?? 'https://198.51.100.10'}
                    description={t('inventory.telemetry.urlHint')} inputWrapperOrder={['label', 'input', 'description']}
                    onChange={(e) => set('url', e.currentTarget.value.trim())} />
                </Inherited>
                <Select label={t('inventory.telemetry.verifyTls')} disabled={disabled} allowDeselect={false}
                  value={form.verify_tls} onChange={(v) => set('verify_tls', v ?? '')}
                  data={[{ value: '', label: t('inventory.telemetry.verifyDefault') }, { value: 'true', label: t('inventory.telemetry.verifyYes') },
                    { value: 'false', label: t('inventory.telemetry.verifyNo') }]} />
              </SimpleGrid>
            </Collapse>
          </div>
        </>
      )}

      {canEdit && (
        <SaveBar count={count} saving={busy} onSave={save}
          onDiscard={() => { setForm(start()); setCollect(startCollect()) }} />
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
