import { Anchor, Group, Text, Tooltip } from '@mantine/core'
import { type DataColumn, DataTable } from '@bitsandbricks/ui'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { telemetryPath } from '@/pages/inventory/model'
import { ago } from '@/lib/time'
import type { DeviceStateRow } from './api'
import { DeviceProblems } from './DeviceTelemetry'
import { METHODS, type MethodCell, type MethodState } from './methods'
import { NEEDS_LOOK } from './state'
import './MethodGrid.css'

export interface GridRow { r: DeviceStateRow; cells: MethodCell[]; agent: ReactNode; agentSort: string }

/** Devices down, ways of reporting across (issue #904): one square per method, its colour and
 *  shape say the state, hovering it says when it was heard and the last error. */
export function MethodGrid({ rows, toolbar }: { rows: GridRow[]; toolbar?: ReactNode }) {
  const { t } = useTranslation()
  const word = (c: MethodCell) => {
    const what = t(`telemetryGrid.method.${c.method}`)
    if (c.state === 'err') {
      const kind = c.problem ? t(`telemetry.problemKind.${c.problem.kind}`, { defaultValue: c.problem.kind }) : ''
      return t('telemetryGrid.tip.err', { what, error: kind })
    }
    if (c.state === 'ok' || c.state === 'late') return t(`telemetryGrid.tip.${c.state}`, { what, when: c.at ? ago(c.at) : t('telemetryGrid.waits') })
    return t(`telemetryGrid.tip.${c.state}`, { what })
  }
  const columns: DataColumn<GridRow>[] = [
    { id: 'name', header: t('telemetryGrid.device'), sort: (g) => g.r.name, cell: (g) => (
      <Group gap={6} wrap="nowrap">
        {g.r.inventory_id
          ? <Anchor component={Link} to={telemetryPath(g.r.inventory_id)} ff="monospace" fw={600}>{g.r.name}</Anchor>
          : <Text span ff="monospace" fw={600}>{g.r.name}</Text>}
        {g.r.kind && <Text span size="xs" c="dimmed">{g.r.kind}</Text>}
        {g.r.pushed && <Text span size="xs" c="dimmed">{t('telemetry.state.pushed')}</Text>}
      </Group>
    ) },
    { id: 'agent', header: t('telemetryGrid.agent'), sort: (g) => g.agentSort, hideOnPhone: true, cell: (g) => g.agent },
    ...METHODS.map((m, i): DataColumn<GridRow> => ({
      id: m, header: t(`telemetryGrid.method.${m}`), width: 72,
      sort: (g) => STATE_ORDER[g.cells[i].state],
      cell: (g) => <Square state={g.cells[i].state} label={word(g.cells[i])} />,
    })),
    { id: 'problem', header: t('telemetryGrid.lastProblem'), hideOnPhone: true, cell: (g) => (
      g.r.problems?.length ? <DeviceProblems problems={g.r.problems.slice(0, 1)} />
        : NEEDS_LOOK.includes(g.r.state) ? <Text span size="sm" c="dimmed">{t(`telemetry.state.${g.r.state}`)}</Text>
          : <Text span size="sm" c="dimmed">–</Text>
    ) },
  ]
  return (
    <>
      <Group justify="space-between" gap="sm" wrap="wrap" mb="sm">
        <Group gap="xs" wrap="wrap">{toolbar}</Group>
        <Legend />
      </Group>
      <DataTable rows={rows} columns={columns} rowKey={(g) => g.r.name} label={t('telemetryGrid.label')} minWidth={820}
        empty={t('telemetry.noMatch')} />
      <Text size="xs" c="dimmed" mt="sm">{t('telemetryGrid.foot')}</Text>
    </>
  )
}

const STATE_ORDER: Record<MethodState, number> = { err: 0, never: 1, late: 2, ok: 3, off: 4 }

function Square({ state, label }: { state: MethodState; label: string }) {
  return (
    <Tooltip label={label}>
      <span role="img" aria-label={label} className={`fb-method-square is-${state}`} />
    </Tooltip>
  )
}

function Legend() {
  const { t } = useTranslation()
  return (
    <Group gap="md" wrap="wrap" aria-label={t('telemetryGrid.legend')}>
      {(['ok', 'late', 'err', 'never', 'off'] as const).map((s) => (
        <Group key={s} gap={6} wrap="nowrap">
          <span aria-hidden className={`fb-method-square is-${s} is-small`} />
          <Text span size="xs" c="dimmed">{t(`telemetryGrid.state.${s}`)}</Text>
        </Group>
      ))}
    </Group>
  )
}
