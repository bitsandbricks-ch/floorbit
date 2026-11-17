import { Alert, Badge, Button, Checkbox, Code, Group, Modal, MultiSelect, Paper, PasswordInput, Select, SimpleGrid, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, post, put } from '@/api/client'
import { ConfirmButton } from '@/components/ConfirmButton'
import { EntitySelect } from '@/components/EntitySelect'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { ago, dateTime } from '@/lib/time'

/** A device telemetry is collected from (floorbit/telemetry/targets.py). Secrets never come back:
 *  ``secrets`` only says which are set. */
export interface TelemetryTarget {
  id: string; name: string; address: string; kind: string; platform: string; drivers: string[]
  snmp_version: '2c' | '3'; sec_name?: string; username?: string; auth_protocol: string; priv_protocol: string
  fdb: string; vlans: number[]; port: number | null; verify_tls: boolean; tables: boolean; mdt_node: string | null
  url: string | null; secrets: string[]
}
interface Seen { seen: number | null; online: boolean; ports: number; macs: number; arp: number; neighbours: number }
export interface TelemetrySettings {
  targets: TelemetryTarget[]; seen: Record<string, Seen>
  status: { collector: 'here' | 'agent'; devices: number; points: number; unknown: number; poll_errors: Record<string, string>
    storage: { mode: string; logs: string | null; keep_days: number | null; errors: Record<string, string> } }
  drivers: string[]; platforms: string[]; kinds: string[]; fdb_modes: string[]
}

const KEY = ['telemetry-settings'] as const
const EMPTY = {
  name: '', address: '', kind: 'switch', platform: 'iosxe', drivers: ['snmp'] as string[], snmp_version: '2c', sec_name: '',
  auth_protocol: 'SHA', priv_protocol: 'AES', fdb: 'qbridge', vlans: '', port: '', verify_tls: true, tables: true,
  mdt_node: '', url: '', username: '', community: '', auth_password: '', priv_password: '', password: '', api_secret: '',
}
type Form = typeof EMPTY
const SECRET_KEYS = ['community', 'auth_password', 'priv_password', 'password', 'api_secret'] as const

function fromTarget(tg: TelemetryTarget): Form {
  return { ...EMPTY, ...tg, sec_name: tg.sec_name ?? '', username: tg.username ?? '', vlans: tg.vlans.join(', '),
    port: tg.port ? String(tg.port) : '', mdt_node: tg.mdt_node ?? '', url: tg.url ?? '' }
}

/** What to send: secrets only when typed (empty keeps the stored one). */
function body(form: Form) {
  const out: Record<string, unknown> = { ...form, port: form.port ? Number(form.port) : null }
  for (const k of SECRET_KEYS) if (!form[k]) delete out[k]
  return out
}

/** Settings > Telemetry: which devices report, how, and what came in (docs/telemetry.md). */
export default function Telemetry() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const data = useQuery({ queryKey: KEY, queryFn: () => get<TelemetrySettings>('/api/settings/telemetry'), refetchInterval: 15_000 })
  const refresh = () => void qc.invalidateQueries({ queryKey: KEY })
  const [editing, setEditing] = useState<string | null>(null)
  const [form, setForm] = useState<Form>(EMPTY)
  const [token, setToken] = useState<string | null>(null)
  const [paste, setPaste] = useState<{ name: string; config: string } | null>(null)
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }))
  const save = useMutation({
    mutationFn: () => editing ? put<TelemetryTarget>(`/api/settings/telemetry/targets/${editing}`, body(form))
      : post<TelemetryTarget>('/api/settings/telemetry/targets', body(form)),
    // Secrets leave the page as soon as they are stored.
    onSuccess: () => { setForm(EMPTY); setEditing(null); refresh() },
  })
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/settings/telemetry/targets/${id}`), onSuccess: refresh })
  const reveal = useMutation({ mutationFn: () => get<{ token: string }>('/api/settings/telemetry/token'), onSuccess: (r) => setToken(r.token) })
  const renew = useMutation({ mutationFn: () => post<{ token: string }>('/api/settings/telemetry/token'), onSuccess: (r) => setToken(r.token) })
  const config = useMutation({
    mutationFn: (tg: TelemetryTarget) => get<{ config: string }>(`/api/settings/telemetry/targets/${tg.id}/device-config`)
      .then((r) => ({ name: tg.name, config: r.config })),
    onSuccess: setPaste,
  })
  const d = data.data
  const has = (driver: string) => form.drivers.includes(driver)
  const snmp = has('snmp') || has('traps')
  const login = has('gnmi') || has('nxapi') || has('restconf')
  const error = save.error || remove.error || reveal.error || renew.error || config.error
  const secretHint = (k: string) => editing && d?.targets.find((x) => x.id === editing)?.secrets.includes(k) ? t('telemetry.secretSet') : undefined
  const options = (list: string[] | undefined, ns: string) => (list ?? []).map((v) => ({ value: v, label: t(`telemetry.${ns}.${v}`, { defaultValue: v }) }))

  return (
    <Layout title={t('telemetry.title')}>
      <PageHead title={t('telemetry.title')} desc={t('telemetry.intro')} />
      <Stack gap="md">
        {d && (
          <Paper withBorder radius="lg" p="md">
            <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
              <Stat label={t('telemetry.collector')} value={t(`telemetry.collectorIs.${d.status.collector}`)} />
              <Stat label={t('telemetry.storage')} value={t(`telemetry.storageIs.${d.status.storage.mode}`, { days: d.status.storage.keep_days })} />
              <Stat label={t('telemetry.devices')} value={String(d.status.devices)} />
              <Stat label={t('telemetry.points')} value={String(d.status.points)} />
            </SimpleGrid>
            {Object.entries({ ...d.status.poll_errors, ...d.status.storage.errors }).map(([what, msg]) => (
              <Alert key={what} mt="sm" color="warn" title={what}>{msg}</Alert>
            ))}
          </Paper>
        )}
        <Paper withBorder radius="lg" p="md">
          {!d?.targets.length ? <Text c="dimmed">{t('telemetry.empty')}</Text> : (
            <Table.ScrollContainer minWidth={520}>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t('telemetry.device')}</Table.Th><Table.Th>{t('telemetry.drivers')}</Table.Th>
                    <Table.Th>{t('telemetry.lastSeen')}</Table.Th><Table.Th visibleFrom="sm">{t('telemetry.what')}</Table.Th><Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {d.targets.map((tg) => {
                    const s = d.seen[tg.name]
                    return (
                      <Table.Tr key={tg.id}>
                        <Table.Td><Text ff="monospace" size="sm">{tg.name}</Text><Text size="xs" c="dimmed">{tg.address} · {t(`telemetry.platform.${tg.platform}`, { defaultValue: tg.platform })}</Text></Table.Td>
                        <Table.Td><Group gap={4}>{tg.drivers.map((x) => <Badge key={x} variant="light" size="sm">{t(`telemetry.driver.${x}`, { defaultValue: x })}</Badge>)}</Group></Table.Td>
                        <Table.Td>
                          {s?.seen ? <Badge color={s.online ? 'up' : 'down'} variant="light" tt="none" miw="max-content" title={dateTime(s.seen)}>{ago(s.seen)}</Badge>
                            : <Text size="sm" c="dimmed">{t('telemetry.never')}</Text>}
                        </Table.Td>
                        <Table.Td visibleFrom="sm"><Text size="sm">{s ? t('telemetry.counts', { ...s }) : '–'}</Text></Table.Td>
                        <Table.Td>
                          <Group gap={6} justify="flex-end" wrap="nowrap">
                            <Button size="compact-sm" variant="default" onClick={() => config.mutate(tg)}>{t('telemetry.deviceConfig')}</Button>
                            <Button size="compact-sm" variant="default" onClick={() => { setEditing(tg.id); setForm(fromTarget(tg)) }}>{t('telemetry.edit')}</Button>
                            <ConfirmButton size="compact-sm" variant="subtle" danger label={t('telemetry.remove')}
                              question={t('telemetry.removeQuestion', { name: tg.name })} onConfirm={() => remove.mutate(tg.id)} />
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    )
                  })}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
        </Paper>

        <Paper withBorder radius="lg" p="md">
          <Stack gap="sm">
            <Title order={3} size="h4">{editing ? t('telemetry.editTitle', { name: form.name }) : t('telemetry.addTitle')}</Title>
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
              <Select label={t('telemetry.kind')} data={options(d?.kinds, 'kinds')} value={form.kind} allowDeselect={false}
                onChange={(v) => set('kind', v ?? 'switch')} />
              <EntitySelect kind={form.kind === 'firewall' ? 'firewalls' : 'switches'} label={t('telemetry.device')} required
                value={form.name} onChange={(v) => set('name', v)} />
              <TextInput label={t('telemetry.address')} description={t('telemetry.addressHint')} inputWrapperOrder={['label', 'input', 'description']}
                value={form.address} onChange={(e) => set('address', e.currentTarget.value)} />
              <Select label={t('telemetry.platformLabel')} data={options(d?.platforms, 'platform')} value={form.platform} allowDeselect={false}
                onChange={(v) => set('platform', v ?? 'other')} />
              <MultiSelect label={t('telemetry.drivers')} data={options(d?.drivers, 'driver')} value={form.drivers}
                onChange={(v) => set('drivers', v)} style={{ gridColumn: 'span 2' }} />
            </SimpleGrid>
            {snmp && (
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                <Select label={t('telemetry.snmpVersion')} data={[{ value: '2c', label: 'v2c' }, { value: '3', label: 'v3' }]}
                  value={form.snmp_version} allowDeselect={false} onChange={(v) => set('snmp_version', v ?? '2c')} />
                {form.snmp_version === '2c' ? (
                  <PasswordInput label={t('telemetry.community')} autoComplete="new-password" placeholder={secretHint('community')}
                    value={form.community} onChange={(e) => set('community', e.currentTarget.value)} />
                ) : (<>
                  <TextInput label={t('telemetry.secName')} value={form.sec_name} onChange={(e) => set('sec_name', e.currentTarget.value)} />
                  <Select label={t('telemetry.authProtocol')} data={['MD5', 'SHA', 'SHA224', 'SHA256', 'SHA384', 'SHA512']} value={form.auth_protocol}
                    allowDeselect={false} onChange={(v) => set('auth_protocol', v ?? 'SHA')} />
                  <PasswordInput label={t('telemetry.authPassword')} autoComplete="new-password" placeholder={secretHint('auth_password')}
                    value={form.auth_password} onChange={(e) => set('auth_password', e.currentTarget.value)} />
                  <Select label={t('telemetry.privProtocol')} data={['DES', 'AES', 'AES192', 'AES256']} value={form.priv_protocol}
                    allowDeselect={false} onChange={(v) => set('priv_protocol', v ?? 'AES')} />
                  <PasswordInput label={t('telemetry.privPassword')} autoComplete="new-password" placeholder={secretHint('priv_password')}
                    value={form.priv_password} onChange={(e) => set('priv_password', e.currentTarget.value)} />
                </>)}
                <Select label={t('telemetry.fdb')} data={options(d?.fdb_modes, 'fdbMode')} value={form.fdb} allowDeselect={false}
                  onChange={(v) => set('fdb', v ?? 'qbridge')} />
                {form.fdb === 'cisco_vlans' && (
                  <TextInput label={t('telemetry.vlans')} description={t('telemetry.vlansHint')} placeholder="10, 20, 30"
                    inputWrapperOrder={['label', 'input', 'description']} value={form.vlans} onChange={(e) => set('vlans', e.currentTarget.value)} />
                )}
                <Checkbox mt="lg" label={t('telemetry.tables')} checked={form.tables} onChange={(e) => set('tables', e.currentTarget.checked)} />
              </SimpleGrid>
            )}
            {(login || has('opnsense')) && (
              <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                <TextInput label={has('opnsense') && !login ? t('telemetry.apiKey') : t('telemetry.username')} autoComplete="off"
                  value={form.username} onChange={(e) => set('username', e.currentTarget.value)} />
                {has('opnsense') && !login ? (
                  <PasswordInput label={t('telemetry.apiSecret')} autoComplete="new-password" placeholder={secretHint('api_secret')}
                    value={form.api_secret} onChange={(e) => set('api_secret', e.currentTarget.value)} />
                ) : (
                  <PasswordInput label={t('telemetry.password')} autoComplete="new-password" placeholder={secretHint('password')}
                    value={form.password} onChange={(e) => set('password', e.currentTarget.value)} />
                )}
                <TextInput label={t('telemetry.port')} placeholder={t('telemetry.portDefault')} value={form.port}
                  onChange={(e) => set('port', e.currentTarget.value.replace(/\D/g, ''))} />
                <Checkbox mt="lg" label={t('telemetry.verifyTls')} checked={form.verify_tls} onChange={(e) => set('verify_tls', e.currentTarget.checked)} />
              </SimpleGrid>
            )}
            {has('mdt') && (
              <TextInput label={t('telemetry.mdtNode')} description={t('telemetry.mdtNodeHint')} inputWrapperOrder={['label', 'input', 'description']}
                value={form.mdt_node} onChange={(e) => set('mdt_node', e.currentTarget.value)} />
            )}
            {error && <Alert color="down" role="alert">{error.message}</Alert>}
            {save.isSuccess && <Alert color="up">{t('telemetry.saved', { name: save.data.name })}</Alert>}
            <Group justify="flex-end">
              {editing && <Button variant="default" onClick={() => { setEditing(null); setForm(EMPTY) }}>{t('telemetry.cancel')}</Button>}
              <Button loading={save.isPending} disabled={!form.name || !form.address.trim() || !form.drivers.length}
                onClick={() => save.mutate()}>{t('telemetry.save')}</Button>
            </Group>
          </Stack>
        </Paper>

        <Paper withBorder radius="lg" p="md">
          <Stack gap="sm">
            <Title order={3} size="h4">{t('telemetry.sendersTitle')}</Title>
            <Text size="sm">{t('telemetry.senders')}</Text>
            <Group gap="sm">
              {token ? <Code>{token}</Code> : <Button variant="default" loading={reveal.isPending} onClick={() => reveal.mutate()}>{t('telemetry.showToken')}</Button>}
              <ConfirmButton variant="subtle" danger label={t('telemetry.newToken')} question={t('telemetry.newTokenQuestion')}
                onConfirm={() => renew.mutate()} />
              {d?.status.collector === 'here' && (
                <Button component="a" variant="default" href="/api/settings/telemetry/telegraf.conf">{t('telemetry.download')}</Button>
              )}
            </Group>
          </Stack>
        </Paper>
      </Stack>
      <Modal opened={!!paste} onClose={() => setPaste(null)} title={t('telemetry.pasteTitle', { name: paste?.name })} size="lg">
        <Stack gap="sm">
          <Text size="sm">{t('telemetry.pasteIntro')}</Text>
          {paste?.config ? <Code block>{paste.config}</Code> : <Text c="dimmed">{t('telemetry.pasteNothing')}</Text>}
        </Stack>
      </Modal>
    </Layout>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={0}>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={600}>{value}</Text>
    </Stack>
  )
}
