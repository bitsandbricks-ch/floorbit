import { Badge, Button, Group, Paper, Stack, Text, Title, UnstyledButton } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import type { GameServer, ServiceStatus } from '@/api/types'
import type { ServiceRowData } from './serviceRows'
import { Sparkline } from '@bitsandbricks/ui'
import './ServiceList.css'

/** The service list (issue #889): one row per service, the same on the Services page and on a
 *  dashboard. The page adds the actions (Change, RCON); a dashboard shows the rows as they are. */

const TONE: Record<ServiceStatus, string> = { up: 'up', warn: 'warn', down: 'down', unknown: 'gray' }
const BIT: Record<ServiceStatus, string> = { up: '', warn: 'is-warn', down: 'is-down', unknown: 'is-off' }

/** One service on one line: state, name and where it is, the number that matters, its recent
 *  history and what can be done with it. */
export function ServiceRow({ row: r, showType = false, canRcon = false, onConsole, onSelect, selected = false }: {
  row: ServiceRowData; showType?: boolean; canRcon?: boolean; onConsole?: () => void
  /** Opens the service's details (issue #1337); the whole row is the target, the name the keyboard's. */
  onSelect?: () => void; selected?: boolean
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  // Ask this one game server now instead of waiting for the next poll (after a restart, say).
  const check = useMutation({
    mutationFn: () => post(`/api/game-servers/check/${r.game!.id}`, {}),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.gameServers }),
  })
  const bad = r.status === 'down'
  return (
    <div className="fb-service-row" role="group" aria-label={r.name} data-status={r.status} data-selected={selected || undefined}
      onClick={onSelect ? (e) => { if (!(e.target as HTMLElement).closest('button, a, input')) onSelect() } : undefined}>
      <div className="fb-service-name">
        <span className={`fb-bit ${BIT[r.status]}`} aria-hidden="true" />
        <div style={{ minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            {onSelect
              ? <UnstyledButton onClick={onSelect} aria-expanded={selected} aria-label={t('services.details', { name: r.name })} style={{ minWidth: 0 }}>
                  <Text fw={600} truncate>{r.name}</Text>
                </UnstyledButton>
              : <Text fw={600} truncate>{r.name}</Text>}
            <Badge size="sm" variant="light" color={TONE[r.status]}>{t(`services.status.${r.status}`)}</Badge>
          </Group>
          <Text size="sm" c="dimmed" ff="monospace" truncate>{showType ? `${t(`services.types.${r.type}`)} · ${r.target}` : r.target}</Text>
          {/* On their own line, so a long tag never squeezes the name. */}
          {!!r.tags?.length && (
            <Group gap={4} mt={4} wrap="wrap">
              {r.tags.map((tag) => <Badge key={tag} size="xs" variant="outline" color="gray" tt="none">{tag}</Badge>)}
            </Group>
          )}
        </div>
      </div>
      <div className="fb-service-value">
        {r.value && (
          <Group gap={6} align="baseline" wrap="nowrap">
            <Text fw={700} fz="xl" lh={1}>{r.value}</Text>
            {r.unit && <Text size="sm" c="dimmed">{r.unit}</Text>}
          </Group>
        )}
        {r.note && <Text size="sm" c={bad ? 'down' : r.status === 'warn' && !r.value ? 'warn' : r.status === 'unknown' ? 'dimmed' : undefined} lineClamp={2}>{r.note}</Text>}
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
        {r.elsewhere && <Text size="xs" c="dimmed" ta="right">{r.elsewhere}</Text>}
      </Group>
    </div>
  )
}

/** A titled group of rows, like "Internet lines 2". When every row is set up in the same other
 *  place, the group says where once instead of on each row (ten firewalls, #1419). */
export function ServiceGroup({ title, rows, showType, canRcon, onConsole, onSelect, selected }: {
  title?: string; rows: ServiceRowData[]; showType?: boolean; canRcon?: boolean; onConsole?: (s: GameServer) => void
  onSelect?: (r: ServiceRowData) => void; selected?: string | null
}) {
  const where = rows.length > 1 && rows.every((r) => r.elsewhere && r.elsewhere === rows[0].elsewhere) ? rows[0].elsewhere : null
  const shown = where ? rows.map((r) => ({ ...r, elsewhere: undefined })) : rows
  return (
    <Stack gap="xs" component="section" aria-label={title}>
      {title && (
        <Group gap="xs">
          <Title order={2} size="h4">{title}</Title>
          <Badge variant="default" radius="sm">{rows.length}</Badge>
          {where && <Text size="sm" c="dimmed" className="fb-service-group-note">{where}</Text>}
        </Group>
      )}
      <Paper withBorder className="fb-service-list">
        {shown.map((r) => (
          <ServiceRow key={r.key} row={r} showType={showType} canRcon={canRcon} onConsole={r.game && onConsole ? () => onConsole(r.game!) : undefined}
            onSelect={onSelect ? () => onSelect(r) : undefined} selected={selected === r.key} />
        ))}
      </Paper>
    </Stack>
  )
}
