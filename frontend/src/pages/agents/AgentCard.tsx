import { Anchor, Badge, Group, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { IconChevronRight } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Field } from '@/components/ui'
import { ago } from '@/lib/time'
import { agentHref, type AgentRow } from './data'
import { HintAnchor } from './HintAnchor'
import { behind, PLUGIN_COLOR, pluginSays, plugins, stateKey, upText } from './model'

const SHOWN_PROBLEMS = 3

/** One agent at a glance on the overview: is it there, how it connects, which version, how its
 *  plugins do and what needs a look. Everything else is on its own page. */
export function AgentCard({ row, newest, tagNames }: { row: AgentRow; newest?: string | null; tagNames: Record<string, string> }) {
  const { t, i18n } = useTranslation()
  const { agent: a, problems, tone } = row
  const lang = i18n.language
  const list = plugins(a)
  const drops = Math.max(a.report?.reconnects ?? 0, a.report?.link_drops ?? 0)
  const tags = a.tags?.length ? a.tags.map((x) => tagNames[x] ?? x).join(', ') : t('agents.allDevices')
  const href = agentHref(a.id)

  return (
    <Paper withBorder radius="lg" p="md" component="article" aria-labelledby={`agent-${a.id}`}
      className={`fb-stat-${tone}`} style={{ minWidth: 0 }}>
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start" gap="xs" wrap="nowrap">
          <Title order={3} size="h5" id={`agent-${a.id}`} style={{ overflowWrap: 'anywhere', minWidth: 0 }}>
            <Anchor component={Link} to={href} c="inherit">{a.name}</Anchor>
          </Title>
          <Badge variant="dot" color={tone} tt="none" style={{ flexShrink: 0 }}>{t(`agents.state.${stateKey(a, tone)}`)}</Badge>
        </Group>

        <SimpleGrid cols={{ base: 2, xs: 3 }} spacing="sm" verticalSpacing="xs">
          <Field label={t('agents.fact.seen')}>
            {a.connected ? t('agents.fact.now') : a.last_seen ? ago(a.last_seen, lang) : t('agents.neverSeen')}
          </Field>
          <Field label={t('agents.fact.version')}>
            <Group gap={4} wrap="nowrap">
              <span>{a.version ?? '–'}</span>
              {(a.outdated || behind(a, newest)) && <Badge size="xs" variant="light" color="warn" tt="none">{t('agents.outdated')}</Badge>}
            </Group>
          </Field>
          <Field label={t('agents.fact.link')}>{a.connected ? t(`agents.transport.${a.transport ?? 'elsewhere'}`) : '–'}</Field>
          <Field label={t('agents.fact.up')}>
            <Stack gap={0}>
              <span>{upText(t, a)}</span>
              {drops > 0 && <Text size="xs" c="warn">{t('agents.reconnects', { count: drops })}</Text>}
            </Stack>
          </Field>
          <Field label={t('agents.fact.calls')}>
            {a.stats?.calls ? t('agents.fact.callsValue', { count: a.stats.calls, n: a.stats.calls.toLocaleString(lang), ms: a.stats.median_ms ?? '–' }) : '–'}
          </Field>
          <Field label={t('agents.tags')}>{tags}</Field>
        </SimpleGrid>

        {list.length > 0 && (
          <Group gap={6} wrap="wrap" aria-label={t('agents.pluginsShort')}>
            {list.map(([id, p]) => (
              <Badge key={id} variant="light" color={PLUGIN_COLOR[p.status] ?? 'gray'} tt="none"
                title={[t(p.running ? `agents.pluginStatus.${p.status}` : 'agents.pluginNotRunning'), pluginSays(p, t).text].filter(Boolean).join(' · ')}>
                {id}
              </Badge>
            ))}
          </Group>
        )}

        {problems.length > 0 && (
          <Stack gap={4} aria-label={t('agents.needsLook')}>
            {problems.slice(0, SHOWN_PROBLEMS).map((p, i) => (
              <Text key={i} size="xs" c={p.tone} style={{ overflowWrap: 'anywhere' }}>{p.text}{p.link && <>{' '}<HintAnchor link={p.link} /></>}</Text>
            ))}
            {problems.length > SHOWN_PROBLEMS && (
              <Text size="xs" c="dimmed">{t('agents.moreProblems', { count: problems.length - SHOWN_PROBLEMS })}</Text>
            )}
          </Stack>
        )}

        <Group justify="flex-end" mt="auto">
          <Anchor component={Link} to={href} size="sm" aria-label={t('agents.openNamed', { name: a.name })}>
            <Group gap={2} wrap="nowrap">{t('agents.open')}<IconChevronRight size={14} aria-hidden="true" /></Group>
          </Anchor>
        </Group>
      </Stack>
    </Paper>
  )
}
