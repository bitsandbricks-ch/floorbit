import { Badge, Grid, Group, MultiSelect, SimpleGrid, Stack, Tabs, Text, ThemeIcon, Title } from '@mantine/core'
import { IconServer2 } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { del, patch } from '@/api/client'
import { qk } from '@/api/keys'
import { usePlugins } from '@/api/queries'
import type { Agent } from '@/api/types'
import { DangerZone } from '@/components/ItemPage'
import { Layout } from '@/components/Layout'
import { EmptyState, ErrorBanner, LoadingState, PanelField, StatTile } from '@bitsandbricks/ui'
import { Panel } from '@/components/ui'
import { ago, dateOnly } from '@/lib/time'
import { AgentDevices } from './agents/AgentDevices'
import { DiskBudget } from './agents/AgentDisk'
import { AgentGraphs } from './agents/AgentGraphs'
import { AgentRename, NewKeyButton, PluginsOff, Updates } from './agents/AgentTools'
import { AgentSettingsForm, CertPanel, KeyPanel } from './agents/AgentSettings'
import { Capabilities } from './agents/Capabilities'
import { SelfUpdate } from './agents/SelfUpdate'
import { AgentLog, RecentEvents } from './agents/AgentEvents'
import { FailoverCard } from './agents/Failover'
import { HeaderActions } from './agents/HeaderActions'
import { useAgentSettings, useAgents, useAgentTags } from './agents/data'
import { Blocked, PluginTable, Report } from './agents/Details'
import { HintAnchor } from './agents/HintAnchor'
import { KeyAlert, type Made } from './agents/KeyAlert'
import { behind, stateKey, upText } from './agents/model'

const TABS = ['overview', 'devices', 'graphs', 'plugins', 'updates', 'logs', 'certificate', 'settings'] as const
type Tab = (typeof TABS)[number]

/** One local agent (issue #905): a header with what it is, its role and how it connects, with
 *  Check now, Roll key and More; then tabs for what needs a look and who takes over, the devices it
 *  collects, its numbers over time, its plugins, its own and its plugins' updates, what happened to
 *  it, its key and certificate, and its settings. */
export default function AgentDetail() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { query, data: d, rows } = useAgents()
  const tags = useAgentTags()
  // The agent plugins that exist here, so the Plugins tab can list the ones this agent doesn't run (#1001).
  const available = (usePlugins().data?.plugins ?? []).filter((p) => p.agent)
    .map((p) => ({ id: p.id, name: p.name, enabled: p.enabled }))
  const [params, setParams] = useSearchParams()
  const tab: Tab = (TABS as readonly string[]).includes(params.get('tab') ?? '') ? params.get('tab') as Tab : 'overview'
  const setTab = (v: string | null) => setParams(v && v !== 'overview' ? { tab: v } : {}, { replace: true })
  const settings = useAgentSettings(id)
  const [made, setMade] = useState<Made | null>(null)
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.agents })
  const setTags = useMutation({ mutationFn: (ids: string[]) => patch(`/api/agents/${id}`, { tags: ids }), onSuccess: refresh })
  const revoke = useMutation({
    mutationFn: () => del(`/api/agents/${id}`),
    onSuccess: () => { refresh(); navigate('/settings/agents') },
  })
  const back = { href: '/settings/agents', label: t('agents.title') }
  const row = rows.find((r) => r.agent.id === id)

  if (query.isPending) return <Layout title={t('agents.title')} back={back}><LoadingState rows={3} /></Layout>
  if (!row || !d) {
    return (
      <Layout title={t('agents.title')} back={back}>
        <ErrorBanner error={query.error} />
        <EmptyState title={t('agents.gone')} description={t('agents.goneHelp')} />
      </Layout>
    )
  }
  const { agent: a, problems, tone } = row
  const plugins = a.report?.plugins ?? {}
  const pluginCount = new Set([...Object.keys(plugins), ...available.map((p) => p.id)]).size
  const r = a.report
  const group = d.groups?.find((g) => g.agents.some((x) => x.id === a.id))
  // Primary or standby only means something with a second agent in the group.
  const role = group && group.agents.length > 1 ? group.agents.find((x) => x.id === a.id)?.role : undefined
  const tagText = a.tags?.length ? a.tags.map((x) => tags.names[x] ?? x).join(', ') : t('agents.allDevices')
  const num = (n?: number) => (n ?? 0).toLocaleString(lang)
  const chips = [
    a.version && `${t('agents.fact.version')} ${a.version}`,
    a.connected && t(`agents.transport.${a.transport ?? 'elsewhere'}`),
    a.address,
    tagText,
    a.protocol && t('agents.chip.protocol', { v: a.protocol }),
  ].filter(Boolean) as string[]

  return (
    <Layout title={a.name} back={back}>
      <Stack gap="md">
        <Group align="flex-start" justify="space-between" gap="md" wrap="wrap">
          <Group align="flex-start" gap="md" wrap="nowrap" style={{ minWidth: 0 }}>
            <ThemeIcon size={48} radius="md" variant="default" aria-hidden="true"><IconServer2 size={24} /></ThemeIcon>
            <Stack gap={6} style={{ minWidth: 0 }}>
              <Text size="xs" c="dimmed" tt="uppercase" ff="monospace">{t('agents.kicker')}</Text>
              <Group gap="sm" wrap="wrap" align="center">
                <Title order={2} style={{ overflowWrap: 'anywhere' }}>{a.name}</Title>
                <Badge variant="dot" color={tone} tt="none">{t(`agents.state.${stateKey(a, tone)}`)}</Badge>
                {role && role !== 'offline' && <Badge variant="light" color={role === 'primary' ? 'up' : 'gray'} tt="none">{t(`agentDetail.role.${role}`)}</Badge>}
                {a.connected && <Text size="sm" c="dimmed">{t('agents.chip.up', { time: upText(t, a) })}</Text>}
                {!a.connected && <Text size="sm" c="dimmed">{a.last_seen ? t('agents.seen', { when: ago(a.last_seen, lang) }) : t('agents.neverSeen')}</Text>}
              </Group>
              <Group gap={6} wrap="wrap">
                {chips.map((c) => <Badge key={c} variant="default" tt="none" fw={500}>{c}</Badge>)}
                {(a.outdated || behind(a, d.newest_version)) && <Badge variant="light" color="warn" tt="none">{t('agents.outdated')}</Badge>}
              </Group>
            </Stack>
          </Group>
          <HeaderActions agent={a} onTab={setTab} onRevoke={() => revoke.mutate()} revoking={revoke.isPending} />
        </Group>

        <ErrorBanner error={setTags.error ?? revoke.error} />
        {made && <KeyAlert made={made} onClose={() => setMade(null)} />}

        <Tabs value={tab} onChange={setTab} keepMounted={false}>
          <Tabs.List>
            <Tabs.Tab value="overview">{t('agents.tab.overview')}</Tabs.Tab>
            <Tabs.Tab value="devices">{t('agents.tab.devices')}</Tabs.Tab>
            <Tabs.Tab value="graphs">{t('agents.tab.graphs')}</Tabs.Tab>
            <Tabs.Tab value="plugins">{t('agents.tab.plugins', { count: pluginCount })}</Tabs.Tab>
            <Tabs.Tab value="updates">{t('agents.tab.updates')}</Tabs.Tab>
            <Tabs.Tab value="logs">{t('agentDetail.tab.logs')}</Tabs.Tab>
            <Tabs.Tab value="certificate">{t('agentDetail.tab.certificate')}</Tabs.Tab>
            <Tabs.Tab value="settings">{t('agents.tab.settings')}</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="overview" pt="md">
            <Grid gap="md">
              <Grid.Col span={{ base: 12, lg: 8 }}>
                <Stack gap="md">
                  <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
                    <StatTile label={t('agents.fact.calls')} value={num(a.stats?.calls)}
                      sub={a.stats?.median_ms != null ? t('agents.stat.median', { ms: a.stats.median_ms }) : undefined} />
                    <StatTile label={t('agents.stat.failed')} value={num(a.stats?.failed)} tone={a.stats?.failed ? 'warn' : undefined} />
                    <StatTile label={t('agents.stat.syslog')} value={num(r?.syslog_received)}
                      tone={r?.syslog_dropped ? 'warn' : undefined}
                      sub={r?.syslog_dropped ? t('agents.reportSyslogDropped', { count: r.syslog_dropped, n: num(r.syslog_dropped) }) : t('agents.stat.waiting', { n: num(r?.syslog_backlog) })} />
                    <StatTile label={t('agents.stat.reconnects')} value={num(Math.max(r?.reconnects ?? 0, r?.link_drops ?? 0))}
                      tone={(r?.reconnects ?? 0) > 0 ? 'warn' : undefined} />
                  </SimpleGrid>
                  <Panel title={t('agents.needsLook')} aria-label={t('agents.needsLook')}>
                    <Stack gap={6}>
                      {problems.length === 0 && <Text size="sm" c="dimmed">{t('agents.overview.allGood')}</Text>}
                      {problems.filter((p) => !p.blocked).map((p, i) => <Text key={i} size="sm" c={p.tone} style={{ overflowWrap: 'anywhere' }}>{p.text}{p.link && <>{' '}<HintAnchor link={p.link} /></>}</Text>)}
                      <Blocked agentId={a.id} plugins={plugins} lang={lang} size="sm" />
                    </Stack>
                  </Panel>
                  <Panel title={t('agents.plugins')} padding={0}>
                    <PluginTable plugins={plugins} lang={lang} agentId={a.id} />
                  </Panel>
                </Stack>
              </Grid.Col>
              <Grid.Col span={{ base: 12, lg: 4 }}>
                <Stack gap="md">
                  <Panel title={t('agents.detailsTitle')}>
                    <Stack gap="sm">
                      <PanelField label={t('agents.tags')}>{tagText}</PanelField>
                      <PanelField label={t('agents.fact.address')}>{a.address ?? '–'}</PanelField>
                      <PanelField label={t('agents.fact.relays')}>
                        {[a.relays?.syslog && t('agents.relaySyslog'), a.relays?.flows && t('agents.relayFlows')].filter(Boolean).join(', ') || '–'}
                      </PanelField>
                      <PanelField label={t('agents.fact.enrolled')}>{t('agents.fact.enrolledValue', { date: dateOnly(a.created_at, lang), who: a.created_by ?? '?' })}</PanelField>
                      {a.old_works_until && <Text size="xs" c="warn">{t('agents.oldKeyWorks', { when: dateOnly(a.old_works_until, lang) })}</Text>}
                    </Stack>
                  </Panel>
                  <Panel title={t('agentDetail.failover.title')} aria-label={t('agentDetail.failover.title')}>
                    <FailoverCard agentId={a.id} groups={d.groups} />
                  </Panel>
                  <Panel title={t('agentDetail.events.title')} aria-label={t('agentDetail.events.title')}>
                    <RecentEvents agentId={a.id} onAll={() => setTab('logs')} />
                  </Panel>
                  {a.connected && (
                    <Panel title={t('agentCapabilities.title')} desc={t('agentCapabilities.help')}>
                      <Capabilities have={a.capabilities} />
                    </Panel>
                  )}
                  {r?.disk && (
                    <Panel title={t('agents.disk.title')}>
                      <DiskBudget disk={r.disk} />
                    </Panel>
                  )}
                  {r && (
                    <Panel title={t('agents.reportTitle')}>
                      <Report report={r} lang={lang} />
                    </Panel>
                  )}
                </Stack>
              </Grid.Col>
            </Grid>
          </Tabs.Panel>

          <Tabs.Panel value="devices" pt="md">
            <AgentDevices agentId={a.id} />
          </Tabs.Panel>

          <Tabs.Panel value="graphs" pt="md">
            <AgentGraphs agentId={a.id} />
          </Tabs.Panel>

          <Tabs.Panel value="plugins" pt="md">
            <Stack gap="md">
              <Panel padding={0}><PluginTable plugins={plugins} lang={lang} agentId={a.id} available={available} off={a.plugins_off} /></Panel>
              <Blocked agentId={a.id} plugins={plugins} lang={lang} />
            </Stack>
          </Tabs.Panel>

          <Tabs.Panel value="updates" pt="md">
            <Stack gap="md">
              <Panel title={t('agentSelfUpdate.title')}>
                <SelfUpdate status={a.self_update} report={r?.agent_update} version={a.version} />
              </Panel>
              <Panel title={t('agents.updates.title')}>
                {r?.updates ? <Updates updates={r.updates} /> : <Text size="sm" c="dimmed">{t('agents.updates.none')}</Text>}
              </Panel>
            </Stack>
          </Tabs.Panel>

          <Tabs.Panel value="logs" pt="md">
            <Panel><AgentLog agentId={a.id} /></Panel>
          </Tabs.Panel>

          <Tabs.Panel value="certificate" pt="md">
            <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
              <KeyPanel agent={a} page={settings.data}><NewKeyButton agent={a} onKey={(m) => setMade({ ...m, rotated: true })} /></KeyPanel>
              {settings.data ? <CertPanel agent={a} page={settings.data} /> : <LoadingState rows={2} />}
            </SimpleGrid>
          </Tabs.Panel>

          <Tabs.Panel value="settings" pt="md">
            <SettingsTab agent={a} tagOptions={tags.options} onTags={(ids) => setTags.mutate(ids)}
              onRevoke={() => revoke.mutate()} />
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Layout>
  )
}


/** Its name, tags and plugins; its own settings and plugin settings (Floorbit sets them, the agent's
 *  env wins); revoking it. Its key and certificate have their own tab. */
function SettingsTab({ agent: a, tagOptions, onTags, onRevoke }: {
  agent: Agent; tagOptions: { value: string; label: string }[]; onTags: (ids: string[]) => void; onRevoke: () => void
}) {
  const { t } = useTranslation()
  return (
    <Grid gap="md">
      <Grid.Col span={{ base: 12, lg: 8 }}>
        <AgentSettingsForm agent={a} />
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 4 }}>
        <Stack gap="md">
          <Panel title={t('agents.cfg.generalTitle')}>
            <Stack gap="md">
              <AgentRename agent={a} />
              <MultiSelect label={t('agents.tags')} description={t('agents.tagsHelp')}
                placeholder={a.tags?.length ? undefined : t('agents.allDevices')}
                nothingFoundMessage={t('agents.noTags')} searchable
                data={tagOptions} value={a.tags ?? []} clearable onChange={onTags} />
              <PluginsOff agent={a} />
            </Stack>
          </Panel>
          <DangerZone label={t('agents.revoke')} question={t('agents.revokeQuestion', { name: a.name })} onConfirm={onRevoke} />
        </Stack>
      </Grid.Col>
    </Grid>
  )
}
