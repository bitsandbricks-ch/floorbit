import { Anchor, Badge } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { type DataColumn, DataTable } from '@bitsandbricks/ui'
import type { Incident, IncidentBoard } from '@/api/types'
import { incidentTitle } from '@/lib/incidentTitle'
import { ago } from '@/lib/time'
import { incidentPath, whereOf } from './where'

const STATUS_ORDER = { open: 0, assigned: 1, fixed: 2 } as const
const STATUS_COLOR = { open: 'down', assigned: 'warn', fixed: 'up' } as const

/** The board as one table (issue #887): many incidents at once, sorted by what matters now.
 *  A row opens the incident's page, where the actions are. */
export function IncidentTable({ items, board }: { items: Incident[]; board: IncidentBoard }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const teamNames = Object.fromEntries(board.teams.map((x) => [x.id, x.name]))
  const columns: DataColumn<Incident>[] = [
    {
      id: 'title', header: t('incidentTable.title'), wrap: true,
      sort: (i) => incidentTitle(i.title, t).toLowerCase(),
      text: (i) => incidentTitle(i.title, t),
      cell: (i) => (
        <Anchor component={Link} to={incidentPath(i.id)} fw={600} c="inherit" onClick={(e) => e.stopPropagation()}>
          {incidentTitle(i.title, t)}
        </Anchor>
      ),
    },
    {
      id: 'status', header: t('incidentTable.status'), card: 'inline',
      sort: (i) => STATUS_ORDER[i.status], text: (i) => t(`incidents.status.${i.status}`),
      cell: (i) => <Badge variant="light" color={STATUS_COLOR[i.status]}>{t(`incidents.status.${i.status}`)}</Badge>,
    },
    { id: 'where', header: t('incidentTable.where'), sort: (i) => whereOf(i, t), cell: (i) => whereOf(i, t), card: 'label' },
    {
      id: 'owner', header: t('incidentTable.owner'), card: 'label',
      sort: (i) => i.assignee ?? '', cell: (i) => i.assignee ?? t('incidents.unassigned'),
    },
    {
      id: 'team', header: t('incidentTable.team'), hideOnPhone: true,
      sort: (i) => (i.team ? teamNames[i.team] ?? i.team : ''), cell: (i) => (i.team ? teamNames[i.team] ?? i.team : ''),
    },
    {
      id: 'age', header: t('incidentTable.age'), numeric: true, card: 'inline',
      // Oldest first by default: the one waiting longest is the next job (issue #300).
      sort: (i) => i.created_at, cell: (i) => ago(i.created_at),
    },
  ]
  return (
    <DataTable rows={items} columns={columns} rowKey={(i) => i.id} label={t('incidents.title')} cards urlState
      defaultSort={{ id: 'status' }} minWidth={720} onRowClick={(i) => navigate(incidentPath(i.id))}
      empty={t('incidents.noMatch')} count={(n) => t('incidentTable.count', { count: n })} />
  )
}
