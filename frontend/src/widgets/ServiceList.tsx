import { Badge, Button, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import type { GameServer, ServiceStatus } from '@/api/types'
import type { ServiceRowData } from './serviceRows'
import { Sparkline } from './Sparkline'
import './ServiceList.css'

/** The service list (issue #889): one row per service, the same on the Services page and on a
 *  dashboard. The page adds the actions (Change, RCON); a dashboard shows the rows as they are. */

const TONE: Record<ServiceStatus, string> = { up: 'up', warn: 'warn', down: 'down', unknown: 'gray' }
const BIT: Record<ServiceStatus, string> = { up: '', warn: 'is-warn', down: 'is-down', unknown: 'is-off' }

/** One service on one line: state, name and where it is, the number that matters, its recent
 *  history and what can be done with it. */
export function ServiceRow({ row: r, showType = false, canRcon = false, onConsole }: { row: ServiceRowData; showType?: boolean; canRcon?: boolean; onConsole?: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  // Ask this one game server now instead of waiting for the next poll (after a restart, say).
  const check = useMutation({
    mutationFn: () => post(`/api/game-servers/check/${r.game!.id}`, {}),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.gameServers }),
  })
  const bad = r.status === 'down' || r.status === 'unknown'
  return (
    <div className="fb-service-row" role="group" aria-label={r.name} data-status={r.status}>
      <div className="fb-service-name">
        <span className={`fb-bit ${BIT[r.status]}`} aria-hidden="true" />
        <div style={{ minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            <Text fw={600} truncate>{r.name}</Text>
            <Badge size="sm" variant="light" color={TONE[r.status]}>{t(`services.status.${r.status}`)}</Badge>
          </Group>
          <Text size="sm" c="dimmed" ff="monospace" truncate>{showType ? `${t(`services.types.${r.type}`)} · ${r.target}` : r.target}</Text>
        </div>
      </div>
      <div className="fb-service-value">
        {r.value && (
          <Group gap={6} align="baseline" wrap="nowrap">
            <Text fw={700} fz="xl" lh={1}>{r.value}</Text>
            {r.unit && <Text size="sm" c="dimmed">{r.unit}</Text>}
          </Group>
        )}
        {r.note && <Text size="sm" c={bad ? 'down' : r.status === 'warn' && !r.value ? 'warn' : undefined} lineClamp={2}>{r.note}</Text>}
      </div>
      <div className="fb-service-spark">{r.points.length > 1 && <Sparkline points={r.points} min={0} />}</div>
      <Group gap={4} className="fb-service-actions" wrap="nowrap" justify="flex-end">
        {r.game && canRcon && (
          <>
            <Button size="compact-sm" variant="default" disabled={!r.game.rcon} onClick={onConsole}
              title={r.game.rcon ? undefined : t('gameServers.noRcon')}>{t('gameServers.console')}</Button>
            <Button size="compact-sm" variant="subtle" loading={check.isPending} onClick={() => check.mutate()}>{t('gameServers.checkNow')}</Button>
          </>
        )}
        {r.edit && <Button size="compact-sm" variant="subtle" onClick={r.edit}>{t('services.edit')}</Button>}
      </Group>
    </div>
  )
}

/** A titled group of rows, like "Internet lines 2". */
export function ServiceGroup({ title, rows, showType, canRcon, onConsole }: {
  title?: string; rows: ServiceRowData[]; showType?: boolean; canRcon?: boolean; onConsole?: (s: GameServer) => void
}) {
  return (
    <Stack gap="xs" component="section" aria-label={title}>
      {title && (
        <Group gap="xs">
          <Title order={2} size="h4">{title}</Title>
          <Badge variant="default" radius="sm">{rows.length}</Badge>
        </Group>
      )}
      <Paper withBorder className="fb-service-list">
        {rows.map((r) => (
          <ServiceRow key={r.key} row={r} showType={showType} canRcon={canRcon} onConsole={r.game && onConsole ? () => onConsole(r.game!) : undefined} />
        ))}
      </Paper>
    </Stack>
  )
}
