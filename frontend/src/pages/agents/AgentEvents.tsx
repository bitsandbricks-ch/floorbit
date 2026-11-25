import { Anchor, Group, Stack, Table, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { useAgentEvents, type AgentEvent } from '@/api/agentEvents'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { ago, dateTime } from '@/lib/time'

const who = (e: AgentEvent, t: (k: string) => string) => (e.user === 'agent' ? t('agentDetail.events.byAgent') : e.user || '–')

/** The newest few events, for the overview; "All events" opens the Logs tab. */
export function RecentEvents({ agentId, onAll }: { agentId: string; onAll: () => void }) {
  const { t, i18n } = useTranslation()
  const q = useAgentEvents(agentId, 5)
  if (q.isPending) return <LoadingState rows={2} />
  const events = q.data?.events ?? []
  return (
    <Stack gap={6}>
      <ErrorBanner error={q.error} />
      {events.length === 0 && <Text size="sm" c="dimmed">{t('agentDetail.events.none')}</Text>}
      {events.map((e, i) => (
        <Group key={i} gap="xs" wrap="nowrap" align="baseline" justify="space-between">
          <Text size="sm" c={e.ok ? undefined : 'warn'} style={{ overflowWrap: 'anywhere' }}>{e.action}</Text>
          <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{ago(e.at, i18n.language)}</Text>
        </Group>
      ))}
      {events.length > 0 && <Anchor component="button" type="button" size="sm" onClick={onAll} ta="left">{t('agentDetail.events.all')}</Anchor>}
    </Stack>
  )
}

/** The Logs tab: what the audit log holds about this agent, newest first. */
export function AgentLog({ agentId }: { agentId: string }) {
  const { t, i18n } = useTranslation()
  const q = useAgentEvents(agentId, 200)
  if (q.isPending) return <LoadingState rows={4} />
  const events = q.data?.events ?? []
  return (
    <Stack gap="sm">
      <ErrorBanner error={q.error} />
      <Text size="sm" c="dimmed">{t('agentDetail.events.help')}</Text>
      {events.length === 0 ? <Text size="sm" c="dimmed">{t('agentDetail.events.none')}</Text> : (
        <Table.ScrollContainer minWidth={560}>
          <Table verticalSpacing="xs" aria-label={t('agentDetail.tab.logs')}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={180}>{t('agentDetail.events.when')}</Table.Th>
                <Table.Th>{t('agentDetail.events.what')}</Table.Th>
                <Table.Th w={160}>{t('agentDetail.events.who')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {events.map((e, i) => (
                <Table.Tr key={i}>
                  <Table.Td><Text size="sm" ff="monospace">{e.at ? dateTime(e.at, i18n.language) : '–'}</Text></Table.Td>
                  <Table.Td><Text size="sm" c={e.ok ? undefined : 'warn'} style={{ overflowWrap: 'anywhere' }}>{e.action}</Text></Table.Td>
                  <Table.Td><Text size="sm" c="dimmed">{who(e, t)}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  )
}
