import { Anchor, Badge, Button, Group, NumberInput, PasswordInput, Select, Stack, Switch, TagsInput, Text, TextInput, Tooltip } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentPluginField, AgentSettingField, AgentSettingsPage, SettingSource } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { Advanced, SaveBar } from '@/pages/settings/editor'
import { useAgentSettings, useAgents } from './data'
import { ago, dateOnly } from '@/lib/time'

// Floorbit sets these per agent (floorbit/agent_settings.py); the agent's own env wins.
type Value = string | number | string[] | boolean | null

// What differs between agents comes first; the rest folds under Advanced (#996).
const BASIC = ['telemetry_port', 'log_level']
const ADVANCED = ['log_summary', 'metrics', 'metrics_token', 'buffer_max_mb', 'buffer_max_hours']
const VRRP = ['vrrp_vips', 'vrrp_interface', 'vrrp_prefer', 'vrrp_id', 'vrrp_peers']

function shown(v: unknown): string {
  if (Array.isArray(v)) return v.join(', ')
  if (v === null || v === undefined || v === '') return ''
  return String(v)
}

const fieldId = (key: string) => `agent-setting-${key.replace(/[^a-z0-9]+/gi, '-')}`

/** One input for a setting's type; the row around it carries the label and help. */
function Input({ id, helpId, type, value, onChange, disabled, placeholder, min, max, options, secretSet }: {
  id: string; helpId?: string; type: string; value: Value; onChange: (v: Value) => void; disabled?: boolean
  placeholder?: string; min?: number | null; max?: number | null; options?: { value: string; label: string }[] | null
  secretSet?: boolean
}) {
  const { t } = useTranslation()
  const common = { id, disabled, 'aria-describedby': helpId, w: '100%' }
  if (type === 'int') {
    return <NumberInput {...common} placeholder={placeholder} min={min ?? undefined} max={max ?? undefined} allowDecimal={false}
      value={typeof value === 'number' ? value : value === null || value === '' ? '' : Number(value)}
      onChange={(v) => onChange(v === '' ? null : Number(v))} />
  }
  if (type === 'bool') return <Switch id={id} disabled={disabled} aria-describedby={helpId} checked={value === true} onChange={(e) => onChange(e.currentTarget.checked)} />
  if (type === 'choice') return <Select {...common} data={options ?? []} value={value === null ? null : String(value)} clearable placeholder={placeholder} onChange={(v) => onChange(v)} />
  if (['list', 'names', 'cidrs', 'ips'].includes(type)) {
    return <TagsInput {...common} placeholder={placeholder} value={Array.isArray(value) ? value : []} onChange={(v) => onChange(v.length ? v : null)} />
  }
  if (type === 'secret') {
    return <PasswordInput {...common} autoComplete="new-password" placeholder={secretSet ? t('agents.cfg.secretSet') : placeholder}
      value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.currentTarget.value || null)} />
  }
  return <TextInput {...common} spellCheck={false} placeholder={placeholder} value={typeof value === 'string' || typeof value === 'number' ? String(value) : ''}
    onChange={(e) => onChange(e.currentTarget.value === '' ? null : e.currentTarget.value)} />
}

/** Where a value comes from, said only when it isn't the default, like Settings' rows; the env var sits in a tooltip. */
function Source({ source, env }: { source: SettingSource; env?: string | null }) {
  const { t } = useTranslation()
  if (source === 'default') return null
  const text = <Text size="xs" c="dimmed" data-source={source}>{t(`agents.cfg.source.${source}`)}</Text>
  return source === 'env' && env
    ? <Tooltip label={t('agents.cfg.envTip', { env })} withArrow multiline maw={320}><span tabIndex={0}>{text}</span></Tooltip>
    : text
}

/** A settings row: label, help and state on the left, the control on the right (the shared .fb-setting-row). */
function Row({ id, label, help, dirty, onUndo, onReset, tags, children }: {
  id: string; label: ReactNode; help?: ReactNode; dirty: boolean; onUndo: () => void; onReset?: () => void
  tags?: ReactNode; children: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="fb-setting-row" data-key={id}>
      <div className="fb-setting-about">
        <Text component="label" htmlFor={id} size="sm" fw={500}>{label}</Text>
        {help && <Text id={`${id}-help`} size="xs" c="dimmed">{help}</Text>}
        <Group gap="xs" mt={2}>
          {dirty ? <>
            <Badge size="sm" variant="light" color="warn" tt="none">{t('settings.unsaved')}</Badge>
            <Anchor component="button" type="button" size="xs" onClick={onUndo}>{t('settings.undo')}</Anchor>
          </> : <>
            {tags}
            {onReset && <Anchor component="button" type="button" size="xs" onClick={onReset}>{t('settings.reset')}</Anchor>}
          </>}
        </Group>
      </div>
      <div className="fb-setting-control">{children}</div>
    </div>
  )
}

/** The agent's own settings and the plugin settings that differ on it, saved together with Settings' save bar. */
export function AgentSettingsForm({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useAgentSettings(agent.id)
  const others = useAgents().data?.agents.filter((a) => a.id !== agent.id).length ?? 0
  const [draft, setDraft] = useState<Record<string, Value>>({})
  const [plugDraft, setPlugDraft] = useState<Record<string, Record<string, Value>>>({})
  const [saved, setSaved] = useState(false)
  const save = useMutation({
    mutationFn: () => patch<AgentSettingsPage>(`/api/agents/${agent.id}/settings`, { settings: draft, plugins: plugDraft }),
    onSuccess: (page) => {
      qc.setQueryData([...qk.agents, agent.id, 'settings'], page)
      setDraft({}); setPlugDraft({}); setSaved(true)
      void qc.invalidateQueries({ queryKey: qk.agents, exact: true })
    },
  })
  if (q.isPending) return <LoadingState />
  if (!q.data) return <ErrorBanner error={q.error} />
  const page = q.data
  const reported = agent.report?.settings
  const pending = new Set(reported?.pending ?? [])
  const count = Object.keys(draft).length + Object.values(plugDraft).reduce((n, p) => n + Object.keys(p).length, 0)
  const set = (key: string, v: Value) => { setSaved(false); setDraft((d) => ({ ...d, [key]: v })) }
  const undo = (key: string) => setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => k !== key)))
  const setPlug = (pid: string, key: string, v: Value) => { setSaved(false); setPlugDraft((d) => ({ ...d, [pid]: { ...d[pid], [key]: v } })) }
  const undoPlug = (pid: string, key: string) => setPlugDraft((d) => {
    const left = Object.fromEntries(Object.entries(d[pid] ?? {}).filter(([k]) => k !== key))
    const rest = Object.fromEntries(Object.entries(d).filter(([p]) => p !== pid))
    return Object.keys(left).length ? { ...rest, [pid]: left } : rest
  })

  const byKey = Object.fromEntries(page.fields.map((f) => [f.key, f]))
  const isSet = (key: string) => page.values[key] !== undefined || (reported?.values[key]?.source ?? 'default') !== 'default'
  // Shared addresses only matter with a second agent, or where they're set already.
  const vrrp = others > 0 || VRRP.some(isSet) ? VRRP : []
  const advanced = [...ADVANCED, ...vrrp].filter((k) => byKey[k])

  const row = (f: AgentSettingField) => {
    const id = fieldId(f.key)
    const env = reported?.values[f.key]?.source === 'env'
    const stored = page.values[f.key]
    const dirty = f.key in draft
    const value: Value = dirty ? draft[f.key] : env ? (reported?.values[f.key]?.value ?? '') : stored === true ? null : (stored ?? null)
    const source: SettingSource = env ? 'env' : stored !== undefined ? 'floorbit' : 'default'
    return (
      <Row key={f.key} id={id} label={t(`agents.cfg.field.${f.key}`)} help={t(`agents.cfg.help.${f.key}`)}
        dirty={dirty} onUndo={() => undo(f.key)} onReset={source === 'floorbit' ? () => set(f.key, null) : undefined}
        tags={<>
          <Source source={source} env={f.env} />
          {f.restart && pending.has(f.key) && <Badge size="xs" variant="outline" color="warn" tt="none">{t('agents.cfg.atRestart')}</Badge>}
        </>}>
        <Input id={id} helpId={`${id}-help`} type={f.type} value={value} disabled={env}
          placeholder={shown(f.default) || undefined} min={f.min} max={f.max} secretSet={stored === true}
          options={f.options?.map((o) => ({ value: o, label: t(`agents.cfg.option.${o}`, { defaultValue: o }) }))}
          onChange={(v) => set(f.key, v)} />
      </Row>
    )
  }
  const pluginRow = (pid: string, values: Record<string, unknown>, f: AgentPluginField) => {
    const id = fieldId(`${pid}-${f.key}`)
    const dirty = !!plugDraft[pid] && f.key in plugDraft[pid]
    const value = (dirty ? plugDraft[pid][f.key] : values[f.key] ?? null) as Value
    const fallback = t('agents.cfg.pluginDefault', { value: shown(f.default) || '–' })
    return (
      <Row key={f.key} id={id} label={f.label} help={f.help ? `${f.help} ${fallback}` : fallback}
        dirty={dirty} onUndo={() => undoPlug(pid, f.key)}
        onReset={f.key in values ? () => setPlug(pid, f.key, null) : undefined}
        tags={<Source source={f.key in values ? 'floorbit' : 'default'} />}>
        <Input id={id} helpId={`${id}-help`} type={f.type} value={value} min={f.min} max={f.max} options={f.options}
          placeholder={shown(f.default) || f.placeholder || undefined} onChange={(v) => setPlug(pid, f.key, v)} />
      </Row>
    )
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); if (count) save.mutate() }} autoComplete="off" noValidate>
      <Stack gap="md" pb={count ? 96 : 0}>
        <Panel title={t('agents.cfg.title')} desc={t('agents.cfg.intro')}>
          <Stack gap={0} className="fb-setting-rows">{BASIC.filter((k) => byKey[k]).map((k) => row(byKey[k]))}</Stack>
          {advanced.length > 0 && (
            <Advanced count={advanced.length} hint={t('agents.cfg.advancedHint')}
              open={advanced.some((k) => k in draft)}>
              <Stack gap={0} className="fb-setting-rows">{advanced.map((k) => row(byKey[k]))}</Stack>
            </Advanced>
          )}
        </Panel>
        {page.plugins.map((p) => (
          <Panel key={p.id} title={t('agents.cfg.pluginTitle', { name: p.name })} desc={t('agents.cfg.pluginsIntro')}
            actions={<Anchor component={Link} to={`/settings/plugins/${encodeURIComponent(p.id)}?tab=agents`} size="sm">
              {t('agents.cfg.pluginPage')}</Anchor>}>
            <Stack gap={0} className="fb-setting-rows">{p.fields.map((f) => pluginRow(p.id, p.values, f))}</Stack>
          </Panel>
        ))}
        <HallOnly agent={agent} keys={page.local_only} />
      </Stack>
      <SaveBar count={count} bad={false} saving={save.isPending} error={save.error} saved={saved ? t('agents.cfg.saved') : null}
        onDiscard={() => { setDraft({}); setPlugDraft({}) }} />
    </form>
  )
}

/** What the hall allows: only the agent's env sets it. Said in words; the env var name sits in a tooltip. */
function HallOnly({ agent, keys }: { agent: Agent; keys: string[] }) {
  const { t } = useTranslation()
  const values = agent.report?.settings?.values ?? {}
  const reported = !!agent.report?.settings
  return (
    <Panel title={t('agents.cfg.hallTitle')} desc={t('agents.cfg.hallIntro')}>
      <Stack gap={0} className="fb-setting-rows">
        {keys.map((k) => {
          const value = values[k]?.value
          return (
            <div key={k} className="fb-setting-row" data-key={k}>
              <div className="fb-setting-about">
                <Tooltip label={t('agents.cfg.envTip', { env: k })} withArrow multiline maw={320}>
                  <Text size="sm" fw={500} tabIndex={0} style={{ alignSelf: 'flex-start' }}>
                    {t(`agents.cfg.hall.${k}.label`, { defaultValue: k })}
                  </Text>
                </Tooltip>
                <Text size="xs" c="dimmed">{t(`agents.cfg.hall.${k}.help`, { defaultValue: '' })}</Text>
              </div>
              <div className="fb-setting-control">
                <Text size="sm" c={value ? undefined : 'dimmed'} style={{ overflowWrap: 'anywhere' }}>
                  {value || (!reported ? t('agents.cfg.notReported')
                    : t(`agents.cfg.hall.${k}.unset`, { defaultValue: t('agents.cfg.hallDefault') }))}
                </Text>
              </div>
            </div>
          )
        })}
      </Stack>
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
      </Stack>
    </Panel>
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
