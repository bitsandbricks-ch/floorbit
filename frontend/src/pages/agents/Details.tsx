import { Anchor, Badge, Button, Group, Text } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import type { AgentPluginHealth, AgentReport, AgentStats } from '@/api/types'
import { DataTable } from '@bitsandbricks/ui'
import { ago } from '@/lib/time'
import { HintAnchor } from './HintAnchor'
import { PLUGIN_COLOR, pluginSays, uptime } from './model'

// The long form of one agent, on its own page: calls, what it reports about itself,
// and each plugin's numbers.

export function Stats({ stats, lang }: { stats?: AgentStats; lang: string }) {
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


/** What the agent says about itself: up how long, reconnects, its syslog and NetFlow (floorbit-agent #3). */
export function Report({ report, lang }: { report?: AgentReport | null; lang: string }) {
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
  if (report.captive_shown || report.captive_done) {
    parts.push(t('agents.reportCaptive', { shown: num(report.captive_shown ?? 0), done: num(report.captive_done ?? 0) }))
  }
  if (report.calls_busy) parts.push(<Text span size="xs" c="warn" key="b">{t('agents.reportBusy', { count: report.calls_busy })}</Text>)
  return (
    <Text size="xs" c="dimmed">
      {parts.map((p, i) => <span key={i}>{i > 0 && ' · '}{p}</span>)}
    </Text>
  )
}


/** Logins a plugin stopped trying (lockouts): they need a person, so the card shows them up front. */
export function Blocked({ agentId, plugins, lang, size = 'xs' }: { agentId: string; plugins?: Record<string, AgentPluginHealth>; lang: string; size?: 'xs' | 'sm' }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const unblock = useMutation({
    mutationFn: (b: { plugin: string; device: string; credential: string }) =>
      post(`/api/agent-plugins/${encodeURIComponent(agentId)}/${encodeURIComponent(b.plugin)}/unblock`, { device: b.device, credential: b.credential }),
    onSettled: () => void qc.invalidateQueries({ queryKey: qk.agents }),
  })
  const rows = Object.entries(plugins ?? {}).flatMap(([id, p]) => (p.auth_blocked ?? []).map((b) => ({ id, b })))
  if (!rows.length) return null
  return (
    <>
      {rows.map(({ id, b }) => (
        <Group key={`${id}|${b.device}|${b.credential}|${b.rev}`} gap={6} wrap="wrap" role="alert">
          <Text size={size} c="down" style={{ overflowWrap: 'anywhere', flex: '1 1 220px' }}>
            {t('agents.authBlocked', { device: b.device, credential: b.credential, when: b.since ? ago(b.since, lang) : '?', message: b.message })}
          </Text>
          <Button size="compact-xs" variant="default" disabled={unblock.isPending}
            onClick={() => unblock.mutate({ plugin: id, device: b.device, credential: b.credential })}>
            {t('agents.authClear')}
          </Button>
        </Group>
      ))}
    </>
  )
}

/** A plugin with a part on the agent that this agent didn't report: why not, and where to change it (#1001). */
export interface QuietPlugin { id: string; name: string; enabled: boolean }

function QuietState({ p, offHere }: { p: QuietPlugin; offHere: boolean }) {
  const { t } = useTranslation()
  const why = !p.enabled ? 'offEverywhere' : offHere ? 'offHere' : 'notReported'
  return (
    <>
      <Text size="sm">{t(`agents.quiet.${why}`)}</Text>
      {why !== 'notReported' && (
        <Anchor component={Link} size="xs" to={why === 'offEverywhere' ? `/settings/plugins/${encodeURIComponent(p.id)}` : '?tab=settings'}>
          {t(why === 'offEverywhere' ? 'agents.quiet.turnOn' : 'agents.quiet.agentSettings')}
        </Anchor>
      )}
    </>
  )
}

/** Every plugin the agent runs, one row each: state, its message, all its numbers, the last error. With
 *  ``available``, also the agent plugins it doesn't run, saying why (off, left to another agent). */
export function PluginTable({ plugins = {}, lang, agentId, available = [], off = [], names = {}, label, empty, header }: {
  plugins?: Record<string, AgentPluginHealth>; lang: string; agentId?: string; available?: QuietPlugin[]; off?: string[]
  /** Plugin id to the name to show; without one, the id. */
  names?: Record<string, string>; label?: string; empty?: string; header?: string
}) {
  const { t } = useTranslation()
  const quiet = new Map(available.filter((p) => !plugins[p.id]).map((p) => [p.id, p]))
  // Running ones first, then the rest by name.
  const ids = [...Object.keys(plugins).sort(), ...[...quiet.keys()].sort()]
  // Callers put the table in a Panel without padding; the empty note needs its own.
  if (!ids.length) return <Text size="sm" c="dimmed" p="md">{empty ?? t('agents.noPluginReport')}</Text>
  return (
    <DataTable rows={ids} rowKey={(id) => id} label={label ?? t('agents.plugins')} urlState={false} pageSize={0} bare cards
      columns={[
        { id: 'plugin', header: header ?? t('agents.col.plugin'), card: 'inline',
          cell: (id) => names[id]
            ? <Text size="sm" fw={500} c={plugins[id] ? undefined : 'dimmed'}>{names[id]}</Text>
            : <Badge variant="light" color={plugins[id] ? PLUGIN_COLOR[plugins[id].status] ?? 'gray' : 'gray'} tt="none">{id}</Badge> },
        { id: 'state', header: t('agents.col.state'), card: 'label', wrap: true, cell: (id) => {
          const q = quiet.get(id)
          if (q) return <QuietState p={q} offHere={off.includes(id)} />
          const p = plugins[id]
          const says = pluginSays(p, t, agentId)
          const tone = p.status === 'error' ? 'down' : p.status === 'warning' ? 'warn' : 'dimmed'
          return (
            <>
              <Text size="sm">{p.running ? t(`agents.pluginStatus.${p.status}`) : t('agents.pluginNotRunning')}</Text>
              {says.text && <Text size="xs" c={tone} style={{ overflowWrap: 'anywhere' }}>{says.text}{says.link && <>{' '}<HintAnchor link={says.link} /></>}</Text>}
              {says.detail && <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>{says.detail}</Text>}
            </>
          )
        } },
        { id: 'numbers', header: t('agents.col.numbers'), card: 'label', wrap: true, cell: (id) => (
          <Text size="xs" c="dimmed">
            {Object.entries(plugins[id]?.metrics ?? {}).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v.toLocaleString(lang)}`).join(' · ') || '–'}
          </Text>
        ) },
        { id: 'error', header: t('agents.col.lastError'), card: 'label', wrap: true, cell: (id) => {
          const last = plugins[id]?.errors[plugins[id].errors.length - 1]
          return last ? <Text size="xs" c="down" style={{ overflowWrap: 'anywhere' }}>{last.at ? `${ago(last.at, lang)}: ` : ''}{last.error}</Text> : <Text size="xs" c="dimmed">–</Text>
        } },
      ]} />
  )
}
