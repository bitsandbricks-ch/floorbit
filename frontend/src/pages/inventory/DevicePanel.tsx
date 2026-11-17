import { Alert, Badge, Button, Group, SimpleGrid, Stack, Tabs, Text } from '@mantine/core'
import { IconAlertTriangle, IconPencil } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, patch, post, put } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import { SPEC_FIELDS, type CredentialInfo, type InventoryOverview } from '@/api/types'
import { Field, LoadingState, PanelSection, SidePanel } from '@/components/ui'
import { dateTime } from '@/lib/time'
import { DeviceIcon } from './icons'
import { InterfacesPanel } from './InterfacesPanel'
import { credentialBody, roleIcon, speedLabel } from './model'
import { useDeviceDetail } from './scope'
import { CredentialsEditor, FeaturesEditor, FromLabel, PropertiesEditor, type CredentialDraft } from './ScopeEditors'


export function DevicePanel({ id, overview, sourceName, onClose, onEdit }: {
  id: string; overview: InventoryOverview; sourceName: (id: string) => string; onClose: () => void; onEdit: () => void
}) {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const canSetCreds = useCan('settings.manage')
  const canClear = useCan('ports.act')
  const { data: dev, isPending } = useDeviceDetail(id)
  const [credError, setCredError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const refresh = () => client.invalidateQueries({ queryKey: qk.inventoryAll })
  const url = `/api/inventory/${encodeURIComponent(id)}`
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => patch(url, body),
    onSuccess: () => { void refresh(); setMessage({ ok: true, text: t('inventory.saved') }) },
    onError: (e) => setMessage({ ok: false, text: e.message }),
  })
  const setCred = useMutation({
    mutationFn: (d: CredentialDraft) => put('/api/inventory/credentials', credentialBody('device', id, d)),
    onSuccess: () => { setCredError(null); void refresh() },
    onError: (e) => setCredError(e.message),
  })
  const removeCred = useMutation({
    mutationFn: (c: CredentialInfo) => del(`/api/inventory/credentials/${encodeURIComponent(c.id)}`),
    onSuccess: () => void refresh(),
    onError: (e) => setCredError(e.message),
  })
  const clear = useMutation({
    mutationFn: (credentialId: string | null) => post('/api/inventory/blocks/clear', { device_id: id, credential_id: credentialId }),
    onSuccess: () => void refresh(),
  })

  const icon = dev ? dev.resolved.look.icon.value || roleIcon(dev.role) : 'other'
  const color = dev?.resolved.look.color.value ?? ''
  return (
    <SidePanel
      width={640}
      onClose={onClose}
      title={dev ? <Group gap="sm" wrap="nowrap"><DeviceIcon icon={icon} color={color} />{dev.name}</Group> : t('common.loading')}
      subtitle={dev && [t(`inventory.role.${dev.role}`, { defaultValue: dev.role }), ...dev.resolved.group_path.map((g) => g.name)].join(' · ')}
      actions={canEdit && dev && (
        <Button size="xs" variant="default" leftSection={<IconPencil size={14} />} onClick={onEdit}>{t('inventory.editDetails')}</Button>
      )}
    >
      {isPending || !dev ? <LoadingState /> : (
        <Stack gap="md">
          {dev.blocks.length > 0 && (
            <Alert color="down" icon={<IconAlertTriangle size={18} />} title={t('inventory.blocks.title')}>
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
          {message && <Text size="sm" role="status" className={message.ok ? 'fb-tone-ok' : 'fb-tone-err'}>{message.ok ? '✓' : '✕'} {message.text}</Text>}
          <Tabs defaultValue="overview" keepMounted={false}>
            <Tabs.List>
              <Tabs.Tab value="overview">{t('inventory.tabs.overview')}</Tabs.Tab>
              <Tabs.Tab value="interfaces">{t('inventory.tabs.interfaces')} <Badge size="xs" variant="light" ml={4}>{dev.interfaces.filter((i) => !i.hidden).length}</Badge></Tabs.Tab>
              <Tabs.Tab value="settings">{t('inventory.tabs.settings')}</Tabs.Tab>
              {canEdit && <Tabs.Tab value="credentials">{t('inventory.tabs.credentials')}</Tabs.Tab>}
            </Tabs.List>

            <Tabs.Panel value="overview" pt="md">
              <PanelSection label={t('inventory.tabs.overview')}>
                <SimpleGrid cols={2} spacing="sm">
                  {(['model', 'serial', 'mgmt_ip', 'hall', 'status'] as const).filter((f) => dev[f]).map((f) => (
                    <Field key={f} label={t(`inventory.field.${f}`)}>{dev[f]}</Field>
                  ))}
                  <Field label={t('inventory.placedLabel')}>{dev.placed ? t('inventory.placed') : t('inventory.notPlaced')}</Field>
                </SimpleGrid>
              </PanelSection>
              {SPEC_FIELDS.some((f) => dev[f]) && (
                <PanelSection label={t('inventory.specs')}>
                  <SimpleGrid cols={2} spacing="sm">
                    {SPEC_FIELDS.filter((f) => dev[f]).map((f) => (
                      <Field key={f} label={t(`inventory.field.${f}`)}>{dev[f]}</Field>
                    ))}
                  </SimpleGrid>
                </PanelSection>
              )}
              <PanelSection label={t('inventory.tags.label')}>
                {dev.resolved.tags.length ? (
                  <Group gap={6}>
                    {dev.resolved.tags.map((tag) => (
                      <Badge key={tag.id} tt="none" variant={tag.own ? 'filled' : 'outline'} color={tag.color || 'gray'}>
                        {tag.name}
                      </Badge>
                    ))}
                  </Group>
                ) : <Text size="sm" c="dimmed">{t('inventory.tags.noneOnDevice')}</Text>}
                {dev.resolved.tags.some((x) => !x.own) && <Text size="xs" c="dimmed" mt={4}>{t('inventory.tags.outlineHint')}</Text>}
              </PanelSection>
              <PanelSection label={t('inventory.look.title')}>
                <Group gap="sm">
                  <DeviceIcon icon={icon} color={color} />
                  <Text size="sm">{t(`inventory.icon.${icon}`, { defaultValue: icon })}{color && ` · ${color}`}</Text>
                  <FromLabel from={dev.resolved.look.icon.from} />
                </Group>
              </PanelSection>
              {!!dev.runs_here?.length && (
                <PanelSection label={t('inventory.runsHere.title')}>
                  <Text size="xs" c="dimmed" mb={4}>{t('inventory.runsHere.hint')}</Text>
                  <Group gap={6}>
                    {dev.runs_here.map((r) => (
                      <Badge key={`${r.kind}-${r.id}`} tt="none" variant="light" color={r.kind === 'game-server' ? 'cyan' : 'gray'}>
                        {r.kind === 'game-server' ? t('inventory.runsHere.game') : t('inventory.runsHere.vm')}: {r.name}
                        {r.via && r.via.toLowerCase() !== dev.name.toLowerCase() && ` (${t('inventory.runsHere.via', { name: r.via })})`}
                      </Badge>
                    ))}
                  </Group>
                </PanelSection>
              )}
              {dev.notes && <PanelSection label={t('inventory.field.notes')}><Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{dev.notes}</Text></PanelSection>}
            </Tabs.Panel>

            <Tabs.Panel value="interfaces" pt="md">
              <InterfacesPanel device={dev} canEdit={canEdit} sourceName={sourceName} onChanged={() => void refresh()} />
              {dev.interfaces.some((i) => i.speed_mbps) && (
                <Text size="xs" c="dimmed" mt="xs">
                  {t('inventory.ifaces.summary', {
                    count: dev.interfaces.filter((i) => !i.hidden).length,
                    fastest: speedLabel(Math.max(...dev.interfaces.map((i) => i.speed_mbps ?? 0))),
                  })}
                </Text>
              )}
            </Tabs.Panel>

            <Tabs.Panel value="settings" pt="md">
              <PanelSection label={t('inventory.props.title')}>
                <PropertiesEditor key={JSON.stringify(dev.properties)} value={dev.properties ?? {}} inherited={dev.resolved.properties}
                  canEdit={canEdit} busy={save.isPending} onSave={(properties) => save.mutate({ properties })} />
              </PanelSection>
              <PanelSection label={t('inventory.features.title')}>
                <FeaturesEditor catalog={overview.features} value={dev.features ?? {}} resolved={dev.resolved.features}
                  canEdit={canEdit} busy={save.isPending} onSave={(features) => save.mutate({ features })} />
              </PanelSection>
            </Tabs.Panel>

            {canEdit && (
              <Tabs.Panel value="credentials" pt="md">
                <PanelSection label={t('inventory.creds.title')}>
                  <Text size="sm" c="dimmed" mb="xs">{t('inventory.creds.intro')}</Text>
                  <CredentialsEditor own={dev.own_credentials} inherited={dev.resolved.credentials} overview={overview}
                    canSet={canSetCreds} busy={setCred.isPending} error={credError}
                    onSet={(d) => setCred.mutateAsync(d)} onRemove={(c) => removeCred.mutate(c)} />
                </PanelSection>
              </Tabs.Panel>
            )}
          </Tabs>
        </Stack>
      )}
    </SidePanel>
  )
}
