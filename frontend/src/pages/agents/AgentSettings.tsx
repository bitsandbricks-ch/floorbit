import { Anchor, Badge, Button, Group, NumberInput, PasswordInput, Select, SimpleGrid, Stack, Switch, Table, TagsInput, Text, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentPluginField, AgentSettingField, AgentSettingsPage, SettingSource } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { useAgentSettings } from './data'
import { ago, dateOnly } from '@/lib/time'

// Floorbit sets these per agent (floorbit/agent_settings.py); the agent's own env wins.
type Value = string | number | string[] | boolean | null
const SOURCE_COLOR: Record<SettingSource, string> = { env: 'warn', floorbit: 'up', default: 'gray' }


function SourceBadge({ source }: { source: SettingSource }) {
  const { t } = useTranslation()
  return <Badge size="xs" variant="light" color={SOURCE_COLOR[source]} tt="none">{t(`agents.cfg.source.${source}`)}</Badge>
}

function shown(v: unknown): string {
  if (Array.isArray(v)) return v.join(', ')
  if (v === null || v === undefined || v === '') return ''
  return String(v)
}

/** One input for a setting's type; ``disabled`` when the agent's env sets it. */
function Input({ type, label, value, onChange, disabled, placeholder, min, max, options, description, secretSet }: {
  type: string; label: ReactNode; value: Value; onChange: (v: Value) => void; disabled?: boolean
  placeholder?: string; min?: number | null; max?: number | null; options?: { value: string; label: string }[] | null
  description?: ReactNode; secretSet?: boolean
}) {
  const { t } = useTranslation()
  const common = { label, description, disabled, size: 'sm' as const }
  if (type === 'int') {
    return <NumberInput {...common} placeholder={placeholder} min={min ?? undefined} max={max ?? undefined} allowDecimal={false}
      value={typeof value === 'number' ? value : value === null || value === '' ? '' : Number(value)}
      onChange={(v) => onChange(v === '' ? null : Number(v))} />
  }
  if (type === 'bool') return <Switch {...common} checked={value === true} onChange={(e) => onChange(e.currentTarget.checked)} mt="xs" />
  if (type === 'choice') return <Select {...common} data={options ?? []} value={value === null ? null : String(value)} clearable placeholder={placeholder} onChange={(v) => onChange(v)} />
  if (['list', 'names', 'cidrs', 'ips'].includes(type)) {
    return <TagsInput {...common} placeholder={placeholder} value={Array.isArray(value) ? value : []} onChange={(v) => onChange(v.length ? v : null)} />
  }
  if (type === 'secret') {
    return <PasswordInput {...common} placeholder={secretSet ? t('agents.cfg.secretSet') : placeholder}
      value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.currentTarget.value || null)} />
  }
  return <TextInput {...common} placeholder={placeholder} value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''}
    onChange={(e) => onChange(e.currentTarget.value === '' ? null : e.currentTarget.value)} />
}

/** The agent's own settings and the plugin settings that differ on it, saved together. */
export function AgentSettingsForm({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useAgentSettings(agent.id)
  const [draft, setDraft] = useState<Record<string, Value>>({})
  const [plugDraft, setPlugDraft] = useState<Record<string, Record<string, Value>>>({})
  const save = useMutation({
    mutationFn: () => patch<AgentSettingsPage>(`/api/agents/${agent.id}/settings`, { settings: draft, plugins: plugDraft }),
    onSuccess: (page) => {
      qc.setQueryData([...qk.agents, agent.id, 'settings'], page)
      setDraft({}); setPlugDraft({})
      void qc.invalidateQueries({ queryKey: qk.agents, exact: true })
    },
  })
  if (q.isPending) return <LoadingState />
  if (!q.data) return <ErrorBanner error={q.error} />
  const page = q.data
  const reported = agent.report?.settings
  const pending = new Set(reported?.pending ?? [])
  const dirty = Object.keys(draft).length + Object.values(plugDraft).reduce((n, p) => n + Object.keys(p).length, 0)

  const field = (f: AgentSettingField) => {
    const env = reported?.values[f.key]?.source === 'env'
    const saved = page.values[f.key]
    const value: Value = f.key in draft ? draft[f.key] : env ? (reported?.values[f.key]?.value ?? '') : saved === true ? null : (saved ?? null)
    const source: SettingSource = reported?.values[f.key]?.source ?? (saved !== undefined ? 'floorbit' : 'default')
    const label = (
      <Group gap={6} wrap="wrap" component="span">
        <span>{t(`agents.cfg.field.${f.key}`)}</span>
        <SourceBadge source={source} />
        {f.restart && pending.has(f.key) && <Badge size="xs" variant="outline" color="warn" tt="none">{t('agents.cfg.atRestart')}</Badge>}
      </Group>
    )
    const help = env ? t('agents.cfg.envWins', { env: f.env }) : t(`agents.cfg.help.${f.key}`)
    return (
      <Input key={f.key} type={f.type} label={label} value={value} disabled={env} description={help}
        placeholder={shown(f.default) || undefined} min={f.min} max={f.max} secretSet={saved === true}
        options={f.options?.map((o) => ({ value: o, label: t(`agents.cfg.option.${o}`, { defaultValue: o }) }))}
        onChange={(v) => setDraft((d) => ({ ...d, [f.key]: v }))} />
    )
  }
  const pluginField = (pid: string, values: Record<string, unknown>, f: AgentPluginField) => {
    const mine = plugDraft[pid]?.[f.key]
    const value = (pid in plugDraft && f.key in plugDraft[pid] ? mine : values[f.key] ?? null) as Value
    const set = f.key in values
    return (
      <Input key={f.key} type={f.type} label={
        <Group gap={6} wrap="wrap" component="span"><span>{f.label}</span><SourceBadge source={set ? 'floorbit' : 'default'} /></Group>}
        value={value} min={f.min} max={f.max} options={f.options}
        placeholder={shown(f.default) || f.placeholder || undefined}
        description={t('agents.cfg.pluginDefault', { value: shown(f.default) || '–' })}
        onChange={(v) => setPlugDraft((d) => ({ ...d, [pid]: { ...d[pid], [f.key]: v } }))} />
    )
  }
  const groups: [string, string[]][] = [
    ['general', ['telemetry_port']],
    ['metrics', ['metrics', 'metrics_token']],
    ['buffer', ['buffer_max_mb', 'buffer_max_hours']],
    ['logs', ['log_level', 'log_summary']],
    ['vrrp', ['vrrp_vips', 'vrrp_interface', 'vrrp_prefer', 'vrrp_id', 'vrrp_peers']],
  ]
  const byKey = Object.fromEntries(page.fields.map((f) => [f.key, f]))

  return (
    <Stack gap="md">
      <Panel title={t('agents.cfg.title')} desc={t('agents.cfg.intro')}>
        <Stack gap="lg">
          {groups.map(([g, keys]) => (
            <Stack key={g} gap="xs">
              <Text size="sm" fw={600}>{t(`agents.cfg.group.${g}`)}</Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md" verticalSpacing="sm">
                {keys.filter((k) => byKey[k]).map((k) => field(byKey[k]))}
              </SimpleGrid>
            </Stack>
          ))}
        </Stack>
      </Panel>
      {page.plugins.length > 0 && (
        <Panel title={t('agents.cfg.pluginsTitle')} desc={t('agents.cfg.pluginsIntro')}>
          <Stack gap="lg">
            {page.plugins.map((p) => (
              <Stack key={p.id} gap="xs">
                <Text size="sm" fw={600}>{p.name}</Text>
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md" verticalSpacing="sm">
                  {p.fields.map((f) => pluginField(p.id, p.values, f))}
                </SimpleGrid>
              </Stack>
            ))}
          </Stack>
        </Panel>
      )}
      <ErrorBanner error={save.error} />
      <Group justify="flex-end">
        {dirty > 0 && <Button variant="subtle" onClick={() => { setDraft({}); setPlugDraft({}) }}>{t('agents.cancel')}</Button>}
        <Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>{t('agents.cfg.save', { count: dirty })}</Button>
      </Group>
      <HallOnly agent={agent} keys={page.local_only} />
    </Stack>
  )
}

/** What the hall allows: only the agent's env sets it, shown here as the agent reports it. */
function HallOnly({ agent, keys }: { agent: Agent; keys: string[] }) {
  const { t } = useTranslation()
  const values = agent.report?.settings?.values ?? {}
  return (
    <Panel title={t('agents.cfg.hallTitle')} desc={t('agents.cfg.hallIntro')} padding={0}>
      <Table.ScrollContainer minWidth={420}>
        <Table aria-label={t('agents.cfg.hallTitle')} verticalSpacing="xs" horizontalSpacing="md">
          <Table.Tbody>
            {keys.map((k) => (
              <Table.Tr key={k}>
                <Table.Td><Text size="sm" ff="monospace" style={{ overflowWrap: 'anywhere' }}>{k}</Text></Table.Td>
                <Table.Td><Text size="sm" c={values[k]?.value ? undefined : 'dimmed'} style={{ overflowWrap: 'anywhere' }}>
                  {values[k]?.value ?? (agent.report?.settings ? t('agents.cfg.hallDefault') : t('agents.cfg.notReported'))}
                </Text></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Panel>
  )
}

/** The key: the agent fetches a new one itself, or one is made to copy (the agent is away). */
export function KeyPanel({ agent, page, children }: { agent: Agent; page?: AgentSettingsPage; children: ReactNode }) {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const roll = useMutation({
    mutationFn: () => post(`/api/agents/${agent.id}/roll`),
    onSettled: () => void qc.invalidateQueries({ queryKey: qk.agents }),
  })
  const where = agent.report?.settings?.key
  return (
    <Panel title={t('agents.cfg.keyTitle')} desc={t('agents.cfg.keyIntro')}>
      <Stack gap="xs">
        <Text size="sm">
          {t('agents.cfg.keyMade', { when: dateOnly(agent.renewed_at ?? agent.created_at, i18n.language) })}
          {where && ` · ${t(`agents.cfg.keyFrom.${where}`)}`}
        </Text>
        {page?.roll_asked && <Text size="sm" c="warn">{t('agents.cfg.rollWaiting', { when: ago(page.roll_asked, i18n.language) })}</Text>}
        <Group gap="xs">
          <ConfirmButton size="compact-sm" variant="default" label={t('agents.cfg.roll')} danger disabled={!agent.connected}
            question={t('agents.cfg.rollQuestion', { name: agent.name })} loading={roll.isPending} onConfirm={() => roll.mutate()} />
          {children}
        </Group>
        {!agent.connected && <Text size="xs" c="dimmed">{t('agents.cfg.rollOffline')}</Text>}
        <ErrorBanner error={roll.error} />
        {page && <IdentityLine agent={agent} page={page} />}
      </Stack>
    </Panel>
  )
}

/** The agent's own key, which signs every request (floorbit/agent_identity.py); an admin can reset it. */
function IdentityLine({ agent, page }: { agent: Agent; page: AgentSettingsPage }) {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const reset = useMutation({
    mutationFn: () => post(`/api/agents/${agent.id}/identity/reset`),
    onSettled: () => void qc.invalidateQueries({ queryKey: qk.agents }),
  })
  const id = page.identity
  return (
    <Stack gap={4}>
      <Text size="sm" c={id ? undefined : 'warn'}>
        {id
          ? t('agents.cfg.identityPinned', { fingerprint: id.fingerprint.slice(0, 16), when: dateOnly(id.pinned_at, i18n.language),
            until: dateOnly(id.not_after, i18n.language) })
          : t('agents.cfg.identityNone')}
      </Text>
      {id && (
        <Group gap="xs">
          <ConfirmButton size="compact-sm" variant="default" label={t('agents.cfg.identityReset')} danger
            question={t('agents.cfg.identityResetQuestion', { name: agent.name })} loading={reset.isPending}
            onConfirm={() => reset.mutate()} />
        </Group>
      )}
      <ErrorBanner error={reset.error} />
    </Stack>
  )
}

/** The agent's HTTPS certificate: signed by Floorbit's agents CA for the names listed here. */
export function CertPanel({ agent, page }: { agent: Agent; page: AgentSettingsPage }) {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const [names, setNames] = useState<string[] | null>(null)
  const saved = (page.values.cert_names as string[] | undefined) ?? []
  const save = useMutation({
    mutationFn: (list: string[]) => patch<AgentSettingsPage>(`/api/agents/${agent.id}/settings`, { settings: { cert_names: list.length ? list : null } }),
    onSuccess: (p) => { qc.setQueryData([...qk.agents, agent.id, 'settings'], p); setNames(null) },
  })
  const renew = useMutation({
    mutationFn: () => post(`/api/agents/${agent.id}/cert`),
    onSettled: () => void qc.invalidateQueries({ queryKey: qk.agents }),
  })
  const has = agent.report?.settings?.cert
  const suggest = [agent.address, ...(agent.report?.vrrp?.holds ?? [])].filter((x): x is string => !!x)
  return (
    <Panel title={t('agents.cfg.certTitle')} desc={t('agents.cfg.certIntro')}
      actions={<Anchor href="/api/agents/ca.pem" size="sm">{t('agents.cfg.downloadCa')}</Anchor>}>
      <Stack gap="sm">
        {has ? (
          <Group gap="xs" wrap="wrap">
            <SourceBadge source={has.source} />
            <Text size="sm">{t('agents.cfg.certHas', { names: has.names.join(', ') || '–', when: dateOnly(has.not_after, i18n.language) })}</Text>
            {!has.floorbit_ca && <Badge size="xs" variant="light" color="gray" tt="none">{t('agents.cfg.certOther')}</Badge>}
          </Group>
        ) : <Text size="sm" c="dimmed">{t('agents.cfg.certNone')}</Text>}
        {has?.source === 'env' && <Text size="xs" c="dimmed">{t('agents.cfg.certEnv')}</Text>}
        <TagsInput label={t('agents.cfg.field.cert_names')} description={t('agents.cfg.help.cert_names')}
          placeholder={(names ?? saved).length ? undefined : (suggest[0] ?? 'agent.example.com')} value={names ?? saved} onChange={setNames}
          data={suggest} maw={560} />
        <Group gap="xs">
          {names !== null && <Button size="compact-sm" loading={save.isPending} onClick={() => save.mutate(names)}>{t('agents.save')}</Button>}
          <Button size="compact-sm" variant="default" disabled={!saved.length || names !== null} loading={renew.isPending}
            onClick={() => renew.mutate()}>{t('agents.cfg.certNew')}</Button>
          {page.cert_asked && (!page.cert || page.cert_asked > page.cert.issued_at) && (
            <Text size="xs" c="warn">{t('agents.cfg.certWaiting')}</Text>
          )}
        </Group>
        <ErrorBanner error={save.error ?? renew.error} />
      </Stack>
    </Panel>
  )
}
