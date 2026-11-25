import { Badge, Code, Group, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { AgentSelfUpdateReport, SelfUpdateState, SelfUpdateStatus } from '@/api/agentUpdates'
import { ago } from '@/lib/time'

const STATE_COLOR: Record<SelfUpdateState, string> = {
  current: 'up', updating: 'blue', installing: 'blue', approve: 'warn', off: 'gray', image: 'warn',
  pull: 'warn', floorbit: 'gray', refused: 'down', rolled_back: 'down', none: 'gray',
}
const EVENT_COLOR: Record<string, string> = {
  installed: 'blue', kept: 'up', 'rolled back': 'down', refused: 'down', dropped: 'gray',
}
// Where the crew updates by hand: a new image (pull and start again) or an approval on the agent.
const PULL = 'docker compose pull && docker compose up -d'
const APPROVE = 'docker compose exec agent python -m floorbit_agent_boot update approve'

/** The agent's own version: what runs, the newest release, where its update stands, its last steps. */
export function SelfUpdate({ status, report, version }: {
  status?: SelfUpdateStatus; report?: AgentSelfUpdateReport; version?: string | null
}) {
  const { t, i18n } = useTranslation()
  if (!status) return null
  const running = report?.running || version || '?'
  const command = status.state === 'approve' ? APPROVE : ['pull', 'image'].includes(status.state) ? PULL : null
  return (
    <Stack gap={6} aria-label={t('agentSelfUpdate.title')}>
      <Group gap="xs" wrap="wrap">
        <Badge variant="light" color={STATE_COLOR[status.state]} tt="none">{t(`agentSelfUpdate.state.${status.state}`)}</Badge>
        <Text size="sm">
          {t('agentSelfUpdate.runs', { v: running })}
          {status.latest && status.state !== 'current' ? ` · ${t('agentSelfUpdate.latest', { v: status.latest })}` : ''}
        </Text>
      </Group>
      <Text size="xs" c="dimmed">{t(`agentSelfUpdate.help.${status.state}`, { v: status.latest ?? '' })}</Text>
      {status.why && status.state === 'refused' && <Text size="xs" c="down" style={{ overflowWrap: 'anywhere' }}>{status.why}</Text>}
      {command && <Code block>{command}</Code>}
      {report && <Text size="xs" c="dimmed">{t(`agentSelfUpdate.policy.${report.policy}`)}</Text>}
      {(report?.events ?? []).slice(-5).reverse().map((e) => (
        <Group key={`${e.at}-${e.event}-${e.version}`} gap={6} wrap="nowrap" align="flex-start">
          <Badge size="xs" variant="light" color={EVENT_COLOR[e.event] ?? 'gray'} tt="none" style={{ flexShrink: 0 }}>
            {t(`agentSelfUpdate.event.${e.event.replace(' ', '_')}`)}
          </Badge>
          <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
            {e.version} · {ago(e.at, i18n.language)}{e.detail ? ` · ${e.detail}` : ''}
          </Text>
        </Group>
      ))}
    </Stack>
  )
}
