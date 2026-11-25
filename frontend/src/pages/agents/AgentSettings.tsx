import { Anchor, Badge, Button, Group, Stack, TagsInput, Text, Tooltip } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentSettingField, AgentSettingsPage, SettingSource } from '@/api/types'
import { Panel } from '@/components/ui'
import { useLeaveWarning } from '@/components/useLeaveWarning'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { Advanced, SaveBar } from '@/pages/settings/editor'
import { useAgentSettings, useAgents } from './data'
import { Input, Row, Source } from './fields'
import { fieldId, shown, type Value } from './values'
import { ago, dateOnly } from '@/lib/time'
import { ConfirmButton } from '@bitsandbricks/ui'

// Floorbit sets these per agent (floorbit/agent_settings.py); the agent's own env wins.

// What differs between agents comes first; the rest folds under Advanced (#996).
const BASIC = ['hall_url', 'telemetry_port', 'disk_budget_mb', 'log_level']
const ADVANCED = ['log_summary', 'metrics', 'metrics_token', 'buffer_max_hours']
const VRRP = ['vrrp_vips', 'vrrp_interface', 'vrrp_prefer', 'vrrp_id', 'vrrp_peers']

/** The agent's own settings, saved with Settings' save bar. Plugin values that differ on it are set on the plugin's page (#990). */
export function AgentSettingsForm({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useAgentSettings(agent.id)
  const others = useAgents().data?.agents.filter((a) => a.id !== agent.id).length ?? 0
  const [draft, setDraft] = useState<Record<string, Value>>({})
  const [saved, setSaved] = useState(false)
  const count = Object.keys(draft).length
  useLeaveWarning(count > 0)
  const save = useMutation({
    mutationFn: () => patch<AgentSettingsPage>(`/api/agents/${agent.id}/settings`, { settings: draft }),
    onSuccess: (page) => {
      qc.setQueryData([...qk.agents, agent.id, 'settings'], page)
      setDraft({}); setSaved(true)
      void qc.invalidateQueries({ queryKey: qk.agents, exact: true })
    },
  })
  if (q.isPending) return <LoadingState rows={3} />
  if (!q.data) return <ErrorBanner error={q.error} />
  const page = q.data
  const reported = agent.report?.settings
  const pending = new Set(reported?.pending ?? [])
  const set = (key: string, v: Value) => { setSaved(false); setDraft((d) => ({ ...d, [key]: v })) }
  const undo = (key: string) => setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => k !== key)))

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
        {page.plugins.length > 0 && <PluginOverrides plugins={page.plugins} />}
        <HallOnly agent={agent} keys={page.local_only} />
      </Stack>
      <SaveBar count={count} bad={false} saving={save.isPending} error={save.error} saved={saved ? t('agents.cfg.saved') : null}
        onDiscard={() => setDraft({})} />
    </form>
  )
}

/** The plugins whose settings may differ on this agent: what differs, and a link to where it's set. */
function PluginOverrides({ plugins }: { plugins: AgentSettingsPage['plugins'] }) {
  const { t } = useTranslation()
  return (
    <Panel title={t('agents.cfg.pluginsTitle')} desc={t('agents.cfg.pluginsIntro')}>
      <Stack gap={0} className="fb-setting-rows">
        {plugins.map((p) => {
          const set = p.fields.filter((f) => f.key in p.values)
          return (
            <div key={p.id} className="fb-setting-row" data-key={p.id}>
              <div className="fb-setting-about">
                <Text size="sm" fw={500}>{p.name}</Text>
                <Text size="xs" c="dimmed">
                  {set.length ? set.map((f) => `${f.label}: ${shown(p.values[f.key]) || '–'}`).join(' · ') : t('agents.cfg.pluginSame')}
                </Text>
              </div>
              <div className="fb-setting-control">
                <Anchor component={Link} to={`/settings/plugins/${encodeURIComponent(p.id)}?tab=agents`} size="sm">
                  {t('agents.cfg.pluginEdit')}
                </Anchor>
              </div>
            </div>
          )
        })}
      </Stack>
    </Panel>
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

/** The tenant's Let's Encrypt certificate, which every agent of the tenant serves when it can. */
function PublicCertLine({ pc }: { pc: NonNullable<AgentSettingsPage['public_cert']> }) {
  const { t, i18n } = useTranslation()
  if (pc.not_after) {
    return <Text size="sm">{t('agents.cfg.publicHas', { name: pc.name, when: dateOnly(pc.not_after, i18n.language) })}</Text>
  }
  if (pc.waiting) {
    return <Text size="sm" c="dimmed">{t('agents.cfg.publicNotReached', { name: pc.name, why: pc.waiting })}</Text>
  }
  return (
    <Text size="sm" c={pc.error ? 'warn' : 'dimmed'}>
      {pc.error ? t('agents.cfg.publicFailed', { name: pc.name, error: pc.error }) : t('agents.cfg.publicWaiting', { name: pc.name })}
    </Text>
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
            {!has.floorbit_ca && !has.public && <Badge size="xs" variant="light" color="gray" tt="none">{t('agents.cfg.certOther')}</Badge>}
          </Group>
        ) : <Text size="sm" c="dimmed">{t('agents.cfg.certNone')}</Text>}
        {has?.source === 'env' && <Text size="xs" c="dimmed">{t('agents.cfg.certEnv')}</Text>}
        {page.public_cert && <PublicCertLine pc={page.public_cert} />}
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
