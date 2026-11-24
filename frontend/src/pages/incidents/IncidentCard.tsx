import { Anchor, Button, Group, Paper, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { Incident, IncidentBoard, IncidentPeople } from '@/api/types'
import { useNowSeconds } from '@/components/useNowSeconds'
import { ago } from '@/lib/time'
import { incidentTitle } from '@/lib/incidentTitle'
import { IncidentBadges, OwnerLine } from './IncidentFacts'
import { incidentPath } from './where'

export type IncidentChange = Partial<{ status: string; assignee: string | null; team: string | null; note: string
  dismiss: 'not_a_problem'; snooze: number }>

/** One incident on the board: title, where, age, who has it and one main action (issue #887).
 *  Notes, reassigning, the port restart and the history are on the incident's own page. */
export function IncidentCard({
  incident: i,
  board,
  me,
  busy,
  onChange,
  onDispatch,
}: {
  incident: Incident
  board: IncidentBoard
  /** Kept for the board's call; reassigning is on the incident's page now. */
  people?: IncidentPeople | undefined
  me: string | undefined
  busy: boolean
  onChange: (change: IncidentChange) => void
  onDispatch?: () => void
}) {
  const { t } = useTranslation()
  const now = useNowSeconds()
  // A lead sends open incidents out; a tech takes one. Fixed ones can come back.
  const action = !i.can_work ? null
    : i.status === 'fixed' ? { label: t('incidents.reopen'), run: () => onChange({ status: 'open' }), variant: 'default' }
      : i.status === 'open' && !i.assignee && i.can_assign && onDispatch ? { label: t('incidents.sendNearest'), run: onDispatch, variant: 'light' }
        : i.status === 'open' ? { label: t('incidents.take'), run: () => onChange({ status: 'assigned', assignee: me ?? null }), variant: 'filled' }
          : { label: t('incidents.fixed'), run: () => onChange({ status: 'fixed' }), variant: 'default' }

  return (
    <Paper withBorder radius="lg" p="sm" data-incident={i.id}>
      <Stack gap={6}>
        <Group justify="space-between" gap="xs" wrap="nowrap" align="flex-start">
          <Anchor component={Link} to={incidentPath(i.id)} fw={600} c="inherit" style={{ overflowWrap: 'anywhere' }}>
            {incidentTitle(i.title, t)}
          </Anchor>
          <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{ago(i.created_at)}</Text>
        </Group>
        <IncidentBadges i={i} board={board} now={now} />
        <Group justify="space-between" gap="xs" wrap="nowrap">
          <OwnerLine i={i} now={now} />
          {action && (
            <Button size="xs" variant={action.variant} loading={busy} onClick={action.run} style={{ flexShrink: 0 }}>{action.label}</Button>
          )}
        </Group>
      </Stack>
    </Paper>
  )
}
