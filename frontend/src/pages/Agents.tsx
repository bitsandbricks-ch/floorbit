import { Alert, Anchor, Badge, Button, Code, CopyButton, Group, MultiSelect, Paper, Stack, Text, TextInput, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentReport, AgentStats, Hall } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { LoadingState, ErrorBanner } from '@/components/ui'
import { ago } from '@/lib/time'

const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/agent.md'
type Answer = { agents: Agent[]; connected: boolean; max: number; server_version?: string; protocol?: number }
type Made = Agent & { key: string }


function Copy({ value }: { value: string }) {
  const { t } = useTranslation()
  return (
    <CopyButton value={value}>
      {({ copied, copy }) => (
        <Button size="compact-sm" variant="default" onClick={copy}>{copied ? t('agents.copied') : t('agents.copy')}</Button>
      )}
    </CopyButton>
  )
}

function Stats({ stats, lang }: { stats?: AgentStats; lang: string }) {
  const { t } = useTranslation()
  if (!stats) return null
  return (
    <>
      <Text size="xs" c="dimmed">
        {stats.calls ? t('agents.stats', { count: stats.calls, ms: stats.median_ms }) : t('agents.statsNone')}
        {stats.failed > 0 && <>{' · '}<Text span size="xs" c="down">{t('agents.statsFailed', { count: stats.failed })}</Text></>}
      </Text>
      {stats.last_error && (
        <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
          {t('agents.lastError', { when: ago(stats.last_error.at, lang), method: stats.last_error.method, error: stats.last_error.error ?? '?' })}
        </Text>
      )}
    </>
  )
}

function uptime(seconds: number): { key: string; n: number } {
  if (seconds >= 86400) return { key: 'agents.upDays', n: Math.floor(seconds / 86400) }
  if (seconds >= 3600) return { key: 'agents.upHours', n: Math.floor(seconds / 3600) }
  return { key: 'agents.upMinutes', n: Math.max(1, Math.floor(seconds / 60)) }
}

/** What the agent says about itself: up how long, reconnects, its syslog and NetFlow (floorbit-agent #3). */
function Report({ report, lang }: { report?: AgentReport | null; lang: string }) {
  const { t } = useTranslation()
  if (!report) return null
  const num = (n?: number) => (n ?? 0).toLocaleString(lang)
  const parts: React.ReactNode[] = []
  if (report.up_seconds !== undefined) {
    const up = uptime(report.up_seconds)
    parts.push(t(up.key, { count: up.n }))
  }
  // Every dropped link is followed by a reconnect, so adding them up would count each twice.
  const drops = Math.max(report.reconnects ?? 0, report.link_drops ?? 0)
  parts.push(drops ? <Text span size="xs" c="warn" key="r">{t('agents.reconnects', { count: drops })}</Text> : t('agents.noReconnects'))
  if (report.syslog_received) {
    parts.push(t('agents.reportSyslog', { received: num(report.syslog_received), waiting: num(report.syslog_backlog) }))
    if (report.syslog_dropped) parts.push(<Text span size="xs" c="down" key="d">{t('agents.reportSyslogDropped', { count: report.syslog_dropped, n: num(report.syslog_dropped) })}</Text>)
  }
  if (report.flows_packets) parts.push(t('agents.reportFlows', { n: num(report.flows_packets) }))
  if (report.calls_busy) parts.push(<Text span size="xs" c="warn" key="b">{t('agents.reportBusy', { count: report.calls_busy })}</Text>)
  return (
    <Text size="xs" c="dimmed">
      {parts.map((p, i) => <span key={i}>{i > 0 && ' · '}{p}</span>)}
    </Text>
  )
}

/** Local agents for a hosted Floorbit (issue #2): enrol one, see whether it is connected, revoke it. */
export default function Agents() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.agents, queryFn: () => get<Answer>('/api/agents'), refetchInterval: 10_000 })
  const refresh = () => void qc.invalidateQueries({ queryKey: qk.agents })
  const [name, setName] = useState('')
  const [made, setMade] = useState<Made | null>(null)
  const make = useMutation({
    mutationFn: () => post<Made>('/api/agents', { name: name.trim() }),
    onSuccess: (m) => { setMade(m); setName(''); refresh() },
  })
  const revoke = useMutation({ mutationFn: (id: string) => del(`/api/agents/${id}`), onSuccess: refresh })
  const halls = useQuery({ queryKey: qk.halls, queryFn: () => get<{ halls: Hall[] }>('/api/halls') })
  const hallOptions = (halls.data?.halls ?? []).map((h) => ({ value: h.id, label: h.name }))
  const setHalls = useMutation({
    mutationFn: ({ id, ids }: { id: string; ids: string[] }) => patch(`/api/agents/${id}`, { halls: ids }),
    onSuccess: refresh,
  })
  const d = query.data
  const error = query.error ?? revoke.error ?? setHalls.error
  const date = (ts: number) => new Date(ts * 1000).toLocaleDateString(i18n.language)
  const run = made ? [
    'docker run -d --restart on-failure:3 --name floorbit-agent \\',
    `  -e FLOORBIT_URL=${window.location.origin} \\`,
    `  -e FLOORBIT_AGENT_KEY=${made.key} \\`,
    '  -e LIBRENMS_URL=https://librenms.example.com -e LIBRENMS_TOKEN=… \\',
    '  ghcr.io/bitsandbricks-ch/floorbit-agent',
  ].join('\n') : ''

  return (
    <Layout title={t('agents.title')} back={{ href: '/settings', label: t('agents.settings') }}>
      <PageHead title={t('agents.title')} desc={t('agents.intro')} />
      <Stack gap="md">
        <ErrorBanner error={error} />
        {made && (
          <Alert color="up" role="status" withCloseButton onClose={() => setMade(null)} title={t('agents.madeTitle', { name: made.name })}>
            <Stack gap="xs">
              <Text size="sm">{t('agents.madeHelp')}</Text>
              <Group gap="xs" wrap="nowrap">
                <Code style={{ overflowWrap: 'anywhere', minWidth: 0 }}>{made.key}</Code>
                <Copy value={made.key} />
              </Group>
              <Text size="sm" fw={600} mt="xs">{t('agents.runTitle')}</Text>
              <Code block style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{run}</Code>
              <Group><Copy value={run} /></Group>
            </Stack>
          </Alert>
        )}
        {query.isPending ? <LoadingState /> : d && (
          <>
            <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('agents.agents')}</Title>
              {d.agents.length === 0 ? <Text size="sm" c="dimmed">{t('agents.none')}</Text> : (
                <Stack gap="sm">
                  {d.agents.map((a) => (
                    <Group key={a.id} justify="space-between" wrap="wrap" gap="xs">
                      <Stack gap={0} style={{ minWidth: 0 }}>
                        <Group gap={6}>
                          <Text fw={600} style={{ overflowWrap: 'anywhere' }}>{a.name}</Text>
                          <Badge variant="light" color={a.connected ? 'up' : 'gray'} tt="none">
                            {a.connected ? t('agents.connected') : t('agents.notConnected')}
                          </Badge>
                          {a.outdated && <Badge variant="light" color="warn" tt="none">{t('agents.outdated')}</Badge>}
                          {a.relays?.syslog && <Badge variant="light" color="gray" tt="none">{t('agents.relaySyslog')}</Badge>}
                          {a.relays?.flows && <Badge variant="light" color="gray" tt="none">{t('agents.relayFlows')}</Badge>}
                        </Group>
                        <Text size="xs" c="dimmed">
                          {a.last_seen ? t('agents.seen', { when: ago(a.last_seen, i18n.language) }) : t('agents.neverSeen')}
                          {a.version && <>{' · '}{t('agents.version', { v: a.version })}</>}
                          {' · '}{t('agents.made', { date: date(a.created_at), who: a.created_by ?? '?' })}
                        </Text>
                        <Stats stats={a.stats} lang={i18n.language} />
                        <Report report={a.report} lang={i18n.language} />
                        {a.outdated && <Text size="xs" c="warn">{t('agents.outdatedHelp', { v: d.protocol ?? '' })}</Text>}
                        {hallOptions.length > 1 && (
                          <MultiSelect size="xs" mt={6} maw={420} label={t('agents.halls')} placeholder={a.halls?.length ? undefined : t('agents.allHalls')}
                            data={hallOptions} value={a.halls ?? []} clearable
                            onChange={(ids) => setHalls.mutate({ id: a.id, ids })} />
                        )}
                      </Stack>
                      <ConfirmButton size="compact-sm" variant="default" danger label={t('agents.revoke')}
                        question={t('agents.revokeQuestion', { name: a.name })} onConfirm={() => revoke.mutate(a.id)} />
                    </Group>
                  ))}
                  <Text size="xs" c="dimmed">{t('agents.inUse')}</Text>
                  {hallOptions.length > 1 && <Text size="xs" c="dimmed">{t('agents.hallsHelp')}</Text>}
                </Stack>
              )}
            </Paper>
            {d.agents.length < d.max && (
              <Paper withBorder radius="lg" p="md">
                <Title order={2} size="h4" mb="xs">{t('agents.new')}</Title>
                <Stack gap="sm">
                  <TextInput label={t('agents.name')} description={t('agents.nameHelp')} value={name} maxLength={60}
                    onChange={(e) => setName(e.currentTarget.value)} />
                  {make.error && <Alert color="down" role="alert">{make.error.message}</Alert>}
                  <Group justify="flex-end">
                    <Button loading={make.isPending} disabled={!name.trim()} onClick={() => make.mutate()}>{t('agents.make')}</Button>
                  </Group>
                </Stack>
              </Paper>
            )}
            <Text size="sm" c="dimmed"><Anchor href={DOCS} underline="always">{t('agents.docs')}</Anchor></Text>
          </>
        )}
      </Stack>
    </Layout>
  )
}
