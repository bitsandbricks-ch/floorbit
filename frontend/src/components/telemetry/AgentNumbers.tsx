import { Badge, Group, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { StateBadge } from '@/components/State'

/** One agent's telemetry numbers, as its last report said (GET /api/telemetry/overview, status.agents). */
export interface TelemetryAgentNumbers {
  id: string; name: string; connected: boolean; status: string; primary: boolean
  points: number; series: number; sent: number; heard: number; failing: number
  quiet: number | null; refused: number; bad_lines: number
}

/** Is Telegraf posting to each agent, and does the agent forward to Floorbit? No layout of its own. */
export function TelemetryAgentNumbersList({ agents }: { agents: TelemetryAgentNumbers[] }) {
  const { t, i18n } = useTranslation()
  const n = (v: number) => v.toLocaleString(i18n.language)
  if (!agents.length) return null
  return (
    <Stack gap={6}>
      {agents.map((a) => {
        const posting = a.quiet !== null && a.quiet < 180
        return (
          <Group key={a.id} gap="xs" wrap="wrap" aria-label={a.name}>
            <Text size="sm" fw={600}>{a.name}</Text>
            {!a.primary && <Badge size="sm" variant="light" color="gray">{t('telemetry.agentNumbers.standby')}</Badge>}
            <StateBadge state={!a.connected ? 'disconnected' : posting ? 'up' : 'warn'}
              label={!a.connected ? t('telemetry.agentNumbers.offline') : posting ? t('telemetry.agentNumbers.posting', { s: a.quiet }) : t('telemetry.agentNumbers.quiet')} />
            <Text size="sm" c="dimmed">
              {[t('telemetry.agentNumbers.points', { n: n(a.points) }), t('telemetry.agentNumbers.heard', { n: n(a.heard) }),
                t('telemetry.agentNumbers.series', { n: n(a.series) }), t('telemetry.agentNumbers.sent', { n: n(a.sent) })].join(' · ')}
            </Text>
            {a.failing > 0 && <Text size="sm" c="warn">{t('telemetry.agentNumbers.failing', { n: n(a.failing) })}</Text>}
            {a.refused + a.bad_lines > 0 && (
              <Text size="sm" c="down">{t('telemetry.agentNumbers.refused', { refused: n(a.refused), bad: n(a.bad_lines) })}</Text>
            )}
          </Group>
        )
      })}
    </Stack>
  )
}
