import { Alert, Anchor, Badge, Button, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import { IconAlertTriangle, IconArrowLeft, IconMap, IconPencil } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { del, get, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan, useInventory } from '@/api/queries'
import { SPEC_FIELDS, type CredentialInfo, type DeviceDetail, type InventoryField, type InventoryOverview } from '@/api/types'
import type { EntityOption } from '@/components/EntitySelect'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { PageTabs } from '@bitsandbricks/ui'
import { usePageTab } from '@/components/pageTab'
import { DeviceRawData, DeviceTelemetryActions, DeviceTelemetryStatus } from '@/components/telemetry/DeviceTelemetry'
import { Field, Panel } from '@/components/ui'
import { EmptyState, LoadingState } from '@bitsandbricks/ui'
import { dateTime } from '@/lib/time'
import { PluginPanels } from '@/pages/plugins/PluginPanels'
import { DeviceForm } from './DeviceForm'
import { DeviceIcon } from './icons'
import { DeviceGraphs } from './DeviceGraphs'
import { DeviceLogs } from './DeviceLogs'
import { DriftPanel } from './DriftPanel'
import { InterfacesPanel } from './InterfacesPanel'
import { credentialBody, entryPath, roleIcon, scopePath, speedLabel, statusLabel, typeName, type Draft } from './model'
import { useCustomIcons, useDeviceDetail, useInventoryGroups, useInventoryTypes } from './scope'
import { CredentialsEditor, FeaturesEditor, FromLabel, PropertiesEditor, type CredentialDraft } from './ScopeEditors'
import { useDeviceTelemetry } from './telemetry'
import { TelemetrySettings } from './TelemetrySettings'
import { ConfirmButton, StatusBadge } from '@bitsandbricks/ui'

/** One device's own page (/inventory/devices/<id>): what it is, its ports, telemetry, settings and
 *  logins, each a tab. The inventory list links here; nothing opens a side panel. */
export default function DevicePage() {
  const { t } = useTranslation()
  const id = useParams().id ?? ''
  const detail = useDeviceDetail(id)
  const overview = useInventoryGroups().data
  const dev = detail.data
  if (detail.error) {
    return (
      <Layout title={t('inventory.title')}>
        <EmptyState title={t('inventory.page.notFound')} description={detail.error.message}
          action={<Button component={Link} to="/inventory" variant="default" leftSection={<IconArrowLeft size={16} />}>{t('inventory.page.back')}</Button>} />
      </Layout>
    )
  }
  return (
    <Layout title={dev?.name ?? t('inventory.title')}>
      {!dev || !overview ? <LoadingState rows={6} /> : <DeviceView key={dev.id} dev={dev} overview={overview} />}
    </Layout>
  )
}

function DeviceView({ dev, overview }: { dev: DeviceDetail; overview: InventoryOverview }) {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const navigate = useNavigate()
  const canEdit = useCan('floorplan.edit')
  const canSetCreds = useCan('settings.manage')
  const canClear = useCan('ports.act')
  // Syslog lines name MACs and IPs, so the device's log needs seats.view like the Logs page.
  const canLogs = useCan('seats.view')
  const inventory = useInventory(false).data
  const sourceName = (sid: string) => inventory?.sources.find((s) => s.id === sid)?.name ?? sid
  // The agent list the Telemetry tab's picker shows (cached): an agent by its name.
  const agents = useQuery({ queryKey: qk.options('agents', ''), queryFn: () => get<{ options: EntityOption[] }>('/api/options/agents') }).data?.options
  const [editing, setEditing] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [credError, setCredError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const refresh = () => client.invalidateQueries({ queryKey: qk.inventoryAll })
  const url = `/api/inventory/${encodeURIComponent(dev.id)}`
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch(url, body),
    onSuccess: () => { void refresh(); setMessage({ ok: true, text: t('inventory.saved') }) },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const edit = useMutation({
    mutationFn: (changes: Partial<Draft> & { unlock?: InventoryField[]; [k: string]: unknown }) => patch(url, changes),
    onSuccess: (_d, changes) => {
      void refresh()
      setFormError(null)
      if (!('unlock' in changes)) { setEditing(false); setMessage({ ok: true, text: t('inventory.saved') }) }
    },
    onError: (e) => setFormError(e.message),
  })
  const remove = useMutation({
    mutationFn: () => del(url),
    onSuccess: () => { void refresh(); navigate('/inventory') },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const setCred = useMutation({
    mutationFn: (d: CredentialDraft) => put('/api/inventory/credentials', credentialBody('device', dev.id, d)),
    onSuccess: () => { setCredError(null); void refresh() },
    onError: (e) => setCredError(e.message),
  })
  const removeCred = useMutation({
    mutationFn: (c: CredentialInfo) => del(`/api/inventory/credentials/${encodeURIComponent(c.id)}`),
    onSuccess: () => void refresh(),
    onError: (e) => setCredError(e.message),
  })
  const clear = useMutation({
    mutationFn: (credentialId: string | null) => post('/api/inventory/blocks/clear', { device_id: dev.id, credential_id: credentialId }),
    onSuccess: () => void refresh(),
  })

  const icon = dev.resolved.look.icon.value || roleIcon(dev.role)
  const color = dev.resolved.look.color.value
  const types = useInventoryTypes().data?.types ?? []
  const deviceFields = types.find((x) => x.id === 'device')?.fields ?? []
  const uploaded = useCustomIcons(icon.startsWith('custom-')).data?.icons.find((i) => i.id === icon)
  const visible = dev.interfaces.filter((i) => !i.hidden)
  const agentId = dev.resolved.properties['telemetry.agent']?.value
  const tagsList = useInventoryGroups().data?.tags ?? []
  const byTag = agentId?.startsWith('tag:') ? agentId.slice(4) : null
  const agentName = !agentId ? null : byTag
    ? t('inventory.telemetry.byTag', { tag: tagsList.find((x) => x.id === byTag)?.name ?? byTag })
    : agents?.find((a) => a.value === agentId)?.label ?? agentId
  const telemetryOn = !!dev.resolved.features.telemetry?.on
  const telemetry = useDeviceTelemetry(dev.id)
  // Raw data only where there is any to read: telemetry on, and admins (the API is theirs).
  const rawTab = telemetryOn && canSetCreds
  const tabIds = ['overview', 'interfaces', 'telemetry', ...(rawTab ? ['raw'] : []), 'graphs', ...(canLogs ? ['logs'] : []), 'settings', ...(canEdit ? ['credentials'] : [])]
  const [tab, setTab] = usePageTab(tabIds)
  const tabs = [
    { id: 'overview', label: t('inventory.tabs.overview') },
    { id: 'interfaces', label: t('inventory.tabs.interfaces'), count: visible.length },
    { id: 'telemetry', label: t('inventory.tabs.telemetry') },
    ...(rawTab ? [{ id: 'raw', label: t('inventory.tabs.raw') }] : []),
    { id: 'graphs', label: t('deviceTabs.graphs.tab') },
    ...(canLogs ? [{ id: 'logs', label: t('deviceTabs.logs.tab') }] : []),
    { id: 'settings', label: t('inventory.tabs.settings') },
    ...(canEdit ? [{ id: 'credentials', label: t('inventory.tabs.credentials'), alert: dev.blocks.length ? 'down' as const : null }] : []),
  ]
  const kicker = [t(`inventory.role.${dev.role}`, { defaultValue: dev.role }), ...dev.resolved.group_path.map((g) => g.name)].join(' · ')

  return (
    <>
      <PageHead
        icon={<DeviceIcon icon={icon} color={color} size={28} />}
        eyebrow={kicker}
        title={<Group gap="sm" wrap="wrap" component="span">{dev.name}{dev.status && <StatusBadge size="md" state={dev.status === 'active' ? 'active' : 'idle'} label={statusLabel(t, dev.status)} />}</Group>}
        actions={<>
          {dev.placed && (
            <Button component={Link} to={`/plan?switch=${encodeURIComponent(dev.name)}`} variant="default" leftSection={<IconMap size={16} />}>
              {t('inventory.page.onPlan')}
            </Button>
          )}
          {canEdit && (
            <Button variant="default" leftSection={<IconPencil size={16} />} onClick={() => { setFormError(null); setEditing(true) }}>
              {t('inventory.editDetails')}
            </Button>
          )}
          {canEdit && (
            <ConfirmButton variant="subtle" danger label={dev.sources.length ? t('inventory.hide') : t('inventory.delete')}
              question={dev.sources.length ? t('inventory.deleteFed', { name: dev.name, source: sourceName(dev.sources[0]) })
                : t('inventory.deleteManual', { name: dev.name })}
              onConfirm={() => remove.mutate()} />
          )}
        </>}
      />
      <Group gap={6} mb="md" mt={-8} className="fb-chips">
        {dev.model && <Chip label={t('inventory.field.model')}>{dev.model}</Chip>}
        {dev.mgmt_ip && <Chip label={t('inventory.page.mgmt')} mono>{dev.mgmt_ip}</Chip>}
        {agentName && <Chip label={t('inventory.telemetry.agent')}>{agentName}</Chip>}
        {dev.sources.length === 0 ? <Badge variant="outline" color="gray" tt="none">{t('inventory.manual')}</Badge>
          : dev.sources.map((s) => <Badge key={s} variant="light" color="trace" tt="none">{sourceName(s)}</Badge>)}
        {dev.gone.map((s) => <Badge key={`gone-${s}`} variant="light" color="warn" tt="none">{t('inventory.gone', { source: sourceName(s) })}</Badge>)}
        {dev.hidden && <Badge variant="outline" color="gray" tt="none">{t('inventory.hidden')}</Badge>}
        {!!dev.drift?.length && (
          <Badge variant="light" color="warn" tt="none" role="status">{t('inventoryDrift.count', { count: dev.drift.length })}</Badge>
        )}
      </Group>

      {dev.blocks.length > 0 && (
        <Alert color="down" icon={<IconAlertTriangle size={18} />} title={t('inventory.blocks.title')} mb="md">
          <Stack gap={6}>
            {dev.blocks.map((b) => (
              <Group key={b.credential_id} justify="space-between" wrap="nowrap" align="flex-start">
                <Text size="sm">
                  {t('inventory.blocks.line', {
                    kind: t(`inventory.creds.kinds.${b.kind}`, { defaultValue: b.kind }),
                    by: b.agent ? `${b.plugin} (${b.agent})` : b.plugin || '?',
                    when: dateTime(new Date(b.at * 1000), i18n.language),
                  })}
                  <Text span size="xs" c="dimmed" display="block">{b.message}</Text>
                </Text>
                {canClear && (
                  <Button size="xs" variant="light" loading={clear.isPending} onClick={() => clear.mutate(b.credential_id)}>
                    {t('inventory.blocks.clear')}
                  </Button>
                )}
              </Group>
            ))}
            {!canClear && <Text size="xs">{t('inventory.blocks.techsClear')}</Text>}
          </Stack>
        </Alert>
      )}
      {message && <Text size="sm" role="status" mb="sm" className={message.ok ? 'fb-tone-ok' : 'fb-tone-err'}>{message.ok ? '✓' : '✕'} {message.text}</Text>}

      <PageTabs tabs={tabs} active={tab} onChange={setTab} label={dev.name} />
      <div role="tabpanel" aria-labelledby={`fb-tab-${tab}`} style={{ paddingTop: 'var(--mantine-spacing-md)' }}>
        {tab === 'overview' && (
          <div className="fb-detail-grid">
            <Stack gap="md" style={{ minWidth: 0 }}>
              <Panel title={t('inventory.page.details')}>
                <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="sm">
                  {(['model', 'serial', 'mgmt_ip', 'hall', 'location', 'status'] as const).filter((f) => dev[f]).map((f) => (
                    <Field key={f} label={t(`inventory.field.${f}`)}>{f === 'status' ? statusLabel(t, dev[f]) : dev[f]}</Field>
                  ))}
                  <Field label={t('inventory.placedLabel')}>{dev.placed ? t('inventory.placed') : t('inventory.notPlaced')}</Field>
                  {SPEC_FIELDS.filter((f) => dev[f]).map((f) => (
                    <Field key={f} label={t(`inventory.field.${f}`)}>{dev[f]}</Field>
                  ))}
                  {deviceFields.map((f) => (
                    <Field key={f.key} label={t(`inventory.types.fieldLabel.${f.key}`, { defaultValue: f.label })}>
                      {(() => { const v = dev.fields?.[f.key] || f.default; return f.kind === 'bool' && v ? t(`inventory.types.${v}`) : v || '–' })()}
                    </Field>
                  ))}
                </SimpleGrid>
              </Panel>
              {!!dev.drift?.length && (
                <Panel title={t('inventoryDrift.title')}>
                  <DriftPanel deviceId={dev.id} rows={dev.drift} canEdit={canEdit} />
                </Panel>
              )}
              {dev.connected && (dev.connected.cables.length + dev.connected.circuits.length + dev.connected.uplinks.length
                + (dev.connected.entries?.length ?? 0) > 0) && (
                <Panel title={t('inventory.connected.title')}>
                  <Stack gap={6}>
                    {dev.connected.uplinks.map((u) => (
                      <Text key={u.id} size="sm">{t('inventory.connected.uplink', { name: u.name, port: u.port })}</Text>
                    ))}
                    {dev.connected.circuits.map((c) => (
                      <Text key={c.id} size="sm">{t('inventory.connected.circuit', { name: c.name, board: c.board || '–' })}{c.phase && ` · ${c.phase}`}{c.rating_a ? ` · ${c.rating_a} A` : ''}</Text>
                    ))}
                    {dev.connected.entries?.map((e) => {
                      const type = types.find((x) => x.id === e.type)
                      return (
                        <Text key={`${e.type}:${e.id}`} size="sm">
                          {type ? typeName(t, type) : e.type}: <Anchor component={Link} to={entryPath(e.type, e.id)} size="sm">{e.name}</Anchor>{e.port && ` · ${e.port}`}
                        </Text>
                      )
                    })}
                    {dev.connected.cables.length > 0 && (
                      <Text size="sm">
                        {t('inventory.connected.cables', { count: dev.connected.cables.length })}{' '}
                        <Anchor href={`/cables?q=${encodeURIComponent(dev.name)}`} size="sm">{t('inventory.connected.showCables')}</Anchor>
                      </Text>
                    )}
                    {dev.connected.cables.slice(0, 8).map((c) => (
                      <Text key={c.id} size="xs" c="dimmed" ff="var(--font-mono)">
                        {[c.port, c.panel && `${c.panel} ${c.panel_port}`.trim(), c.seat].filter(Boolean).join(' → ')}{c.label && `  (${c.label})`}
                      </Text>
                    ))}
                  </Stack>
                </Panel>
              )}
              {!!dev.runs_here?.length && (
                <Panel title={t('inventory.runsHere.title')} desc={t('inventory.runsHere.hint')}>
                  <Group gap={6}>
                    {dev.runs_here.map((r) => (
                      <Badge key={`${r.kind}-${r.id}`} tt="none" variant="light" color={r.kind === 'game-server' ? 'cyan' : 'gray'}>
                        {r.kind === 'game-server' ? t('inventory.runsHere.game') : t('inventory.runsHere.vm')}: {r.name}
                        {r.via && r.via.toLowerCase() !== dev.name.toLowerCase() && ` (${t('inventory.runsHere.via', { name: r.via })})`}
                      </Badge>
                    ))}
                  </Group>
                </Panel>
              )}
              <PluginPanels on="device" target={dev.id} frame={(c) => <Panel>{c}</Panel>} />
            </Stack>
            <Stack gap="md" style={{ minWidth: 0 }}>
              <Panel title={t('inventory.page.belongs')}>
                <Stack gap="sm">
                  <Field label={t('inventory.groups.one')}>
                    {dev.resolved.group_path.length ? (
                      <Group gap={4}>
                        {dev.resolved.group_path.map((g, i) => (
                          <span key={g.id}>{i > 0 && ' › '}<Anchor component={Link} to={scopePath('group', g.id)}>{g.name}</Anchor></span>
                        ))}
                      </Group>
                    ) : t('inventory.groups.none')}
                  </Field>
                  <Field label={t('inventory.tags.label')}>
                    {dev.resolved.tags.length ? (
                      <Group gap={6}>
                        {dev.resolved.tags.map((tag) => (
                          <Badge key={tag.id} tt="none" variant={tag.own ? 'filled' : 'outline'} color={tag.color || 'gray'}
                            component={Link} to={scopePath('tag', tag.id)} style={{ cursor: 'pointer' }}>
                            {tag.name}
                          </Badge>
                        ))}
                      </Group>
                    ) : <Text size="sm" c="dimmed">{t('inventory.tags.noneOnDevice')}</Text>}
                    {dev.resolved.tags.some((x) => !x.own) && <Text size="xs" c="dimmed" mt={4}>{t('inventory.tags.outlineHint')}</Text>}
                  </Field>
                  <Field label={t('inventory.look.title')}>
                    <Group gap="sm">
                      <DeviceIcon icon={icon} color={color} />
                      <Text size="sm">{uploaded?.name ?? t(`inventory.icon.${icon}`, { defaultValue: icon })}{color && ` · ${color}`}</Text>
                      <FromLabel from={dev.resolved.look.icon.from} />
                    </Group>
                  </Field>
                </Stack>
              </Panel>
              {telemetryOn && canSetCreds && (
                <Panel title={t('inventory.tabs.telemetry')}>
                  <DeviceTelemetryStatus name={dev.name} />
                </Panel>
              )}
              {dev.notes && <Panel title={t('inventory.field.notes')}><Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{dev.notes}</Text></Panel>}
            </Stack>
          </div>
        )}

        {tab === 'interfaces' && (
          <Panel>
            <InterfacesPanel device={dev} canEdit={canEdit} sourceName={sourceName} onChanged={() => void refresh()} />
            {dev.interfaces.some((i) => i.speed_mbps) && (
              <Text size="xs" c="dimmed" mt="xs">
                {t('inventory.ifaces.summary', { count: visible.length, fastest: speedLabel(Math.max(...dev.interfaces.map((i) => i.speed_mbps ?? 0))) })}
              </Text>
            )}
          </Panel>
        )}

        {tab === 'telemetry' && (
          <Stack gap="md">
            <Panel title={t('inventory.telemetry.now')}>
              {!telemetryOn ? <Text size="sm" c="dimmed">{t('inventory.telemetry.off')}</Text> : canSetCreds ? (
                <Group justify="space-between" align="flex-start" wrap="wrap" gap="sm">
                  <DeviceTelemetryStatus name={dev.name} />
                  <Group gap={6}><DeviceTelemetryActions name={dev.name} setup raw={false} /></Group>
                </Group>
              ) : <Text size="sm" c="dimmed">{t('inventory.page.telemetryAdmins')}</Text>}
            </Panel>
            <Panel title={t('inventory.telemetry.setup')}>
              {telemetry.error && <Alert color="down" mb="sm">{telemetry.error.message}</Alert>}
              <TelemetrySettings key={JSON.stringify([dev.properties, dev.features])} own={dev.properties ?? {}} ownFeatures={dev.features ?? {}}
                inherited={dev.resolved.properties} resolvedOn={dev.resolved.features.telemetry} info={telemetry.data}
                canEdit={canEdit} busy={save.isPending} onSave={(body) => save.mutate(body)} />
            </Panel>
          </Stack>
        )}

        {tab === 'raw' && rawTab && (
          <Panel title={t('telemetry.raw.title', { name: dev.name })}>
            <DeviceRawData name={dev.name} />
          </Panel>
        )}

        {tab === 'graphs' && <DeviceGraphs name={dev.name} interfaces={dev.interfaces} />}

        {tab === 'logs' && canLogs && <Panel><DeviceLogs name={dev.name} /></Panel>}

        {tab === 'settings' && (
          <Stack gap="md">
            <Panel title={t('inventory.props.title')}>
              <PropertiesEditor key={JSON.stringify(dev.properties)} value={dev.properties ?? {}} inherited={dev.resolved.properties} role={dev.role}
                canEdit={canEdit} busy={save.isPending} onSave={(properties) => save.mutate({ properties })} />
            </Panel>
            <Panel title={t('inventory.features.title')}>
              <FeaturesEditor key={JSON.stringify(dev.features)} catalog={overview.features} value={dev.features ?? {}} resolved={dev.resolved.features} role={dev.role}
                canEdit={canEdit} busy={save.isPending} onSave={(features) => save.mutate({ features })} />
            </Panel>
          </Stack>
        )}

        {tab === 'credentials' && canEdit && (
          <Panel title={t('inventory.creds.title')} desc={t('inventory.creds.intro')}>
            <CredentialsEditor own={dev.own_credentials} inherited={dev.resolved.credentials} overview={overview}
              canSet={canSetCreds} busy={setCred.isPending} error={credError}
              onSet={(d) => setCred.mutateAsync(d)} onRemove={(c) => removeCred.mutate(c)} />
          </Panel>
        )}
      </div>

      {editing && inventory && (
        <DeviceForm device={{ ...dev, drift: dev.drift?.length }} roles={inventory.roles} overview={overview} sourceName={sourceName} opened busy={edit.isPending}
          error={formError} onClose={() => setEditing(false)} onSave={(changes) => edit.mutate(changes)}
          onUnlock={(f) => edit.mutate({ unlock: [f] })} />
      )}
    </>
  )
}

/** A fact under the title: its name small, the value after it. */
function Chip({ label, mono, children }: { label: string; mono?: boolean; children: ReactNode }) {
  return (
    <span className="fb-chip">
      <span className="fb-chip-label">{label}</span>
      <span className="fb-chip-value" style={mono ? { fontFamily: 'var(--font-mono)' } : undefined}>{children}</span>
    </span>
  )
}
