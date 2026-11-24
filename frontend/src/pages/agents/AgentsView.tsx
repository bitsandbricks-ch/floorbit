import { Anchor, Badge, Group, Paper, SimpleGrid, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { StatTile } from '@bitsandbricks/ui'
import type { ViewProps } from '@/pages/monitoring/pages'
import { AgentCard } from './AgentCard'
import { agentHref, useAgents, useHalls, type AgentRow } from './data'
import { stateKey } from './model'

/** The body of the Local agents page: the four figures, then a card per agent. */
export default function AgentsView({ expanded }: ViewProps) {
  const { t } = useTranslation()
  const { query, data: d, rows } = useAgents()
  const halls = useHalls()
  if (query.isPending) return <LoadingState lines />
  if (!d) return <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
  if (!rows.length) {
    return <Paper withBorder radius="lg" p="md"><Text size="sm" c="dimmed">{t('agents.none')}</Text></Paper>
  }
  const look = rows.filter((r) => r.tone !== 'up')
  return (
    <Stack gap="md">
      <Overview rows={rows} />
      {expanded ? (
        <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }} spacing="md" aria-label={t('agents.agents')}>
          {rows.map((r) => <AgentCard key={r.agent.id} row={r} newest={d.newest_version} hallNames={halls.names} />)}
        </SimpleGrid>
      ) : look.length > 0 && (
        <Stack gap={6} aria-label={t('agents.needsLook')}>
          {look.map(({ agent: a, tone, problems }) => (
            <Group key={a.id} gap="xs" wrap="nowrap" align="flex-start">
              <Badge variant="dot" color={tone} tt="none" style={{ flexShrink: 0 }}>{t(`agents.state.${stateKey(a, tone)}`)}</Badge>
              <Text size="sm" style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                <Anchor component={Link} to={agentHref(a.id)} fw={600}>{a.name}</Anchor>
                {problems[0] && <Text span size="xs" c={problems[0].tone}>{' · '}{problems[0].text}</Text>}
              </Text>
            </Group>
          ))}
        </Stack>
      )}
    </Stack>
  )
}

/** Four figures over all agents: how many are there, how many need a look, how the plugins run,
 *  and how the calls went in the last hour. */
function Overview({ rows }: { rows: AgentRow[] }) {
  const { t, i18n } = useTranslation()
  const online = rows.filter((r) => r.agent.connected).length
  const look = rows.filter((r) => r.tone !== 'up')
  const plugins = rows.flatMap((r) => Object.values(r.agent.report?.plugins ?? {}))
  const healthy = plugins.filter((p) => p.status === 'off' || (p.running && p.status === 'ok')).length
  const calls = rows.reduce((n, r) => n + (r.agent.stats?.calls ?? 0), 0)
  const failed = rows.reduce((n, r) => n + (r.agent.stats?.failed ?? 0), 0)
  const num = (n: number) => n.toLocaleString(i18n.language)
  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm" aria-label={t('agents.overview.title')} aria-live="polite">
      <StatTile label={t('agents.overview.online')} value={`${online} / ${rows.length}`}
        tone={online === rows.length ? 'ok' : online ? 'warn' : 'err'} />
      <StatTile label={t('agents.overview.look')} value={num(look.length)}
        tone={look.some((r) => r.tone === 'down') ? 'err' : look.length ? 'warn' : undefined}
        sub={look.length ? look.map((r) => r.agent.name).join(', ') : t('agents.overview.allGood')} />
      <StatTile label={t('agents.overview.plugins')} value={plugins.length ? `${healthy} / ${plugins.length}` : '–'}
        tone={plugins.length && healthy < plugins.length ? 'warn' : undefined}
        sub={plugins.length ? t('agents.overview.pluginsSub') : t('agents.overview.noPlugins')} />
      <StatTile label={t('agents.overview.calls')} value={num(calls)}
        tone={failed ? 'warn' : undefined}
        sub={failed ? t('agents.statsFailed', { count: failed }) : t('agents.overview.noFailed')} />
    </SimpleGrid>
  )
}
