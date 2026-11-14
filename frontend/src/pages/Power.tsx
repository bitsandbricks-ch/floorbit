import { Alert, Badge, Button, Group, Loader, Paper, Progress, Stack, Table, Text, Title } from '@mantine/core'
import { IconBolt, IconPlus, IconRefresh } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { del, get, patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, usePower } from '@/api/queries'
import type { Circuit, PowerBoard, PowerOverview, PowerState } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { BoardDialog, CircuitDialog, ReadingDialog } from './power/Dialogs'

const TONE: Record<PowerState, string> = { ok: 'up', warn: 'warn', crit: 'down', tripped: 'down', unknown: 'gray' }
const ORDER: PowerState[] = ['tripped', 'crit', 'warn', 'ok', 'unknown']
type T = (k: string, o?: Record<string, unknown>) => string

function ago(ts: number, t: T) {
  const mins = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60))
  if (mins < 1) return t('power.justNow')
  if (mins < 60) return t('power.minutesAgo', { count: mins })
  return t('power.hoursAgo', { count: Math.round(mins / 60) })
}

function Load({ c }: { c: Circuit }) {
  const { t } = useTranslation()
  if (c.state === 'tripped') {
    return <Text size="sm" c="var(--color-down)" fw={600}>{t('power.trippedNote', { who: c.tripped?.by ?? '?', ago: ago(c.tripped?.at ?? 0, t) })}</Text>
  }
  if (!c.reading || c.load_pct === null) return <Text size="sm" c="dimmed">{t('power.state.unknown')}</Text>
  const r = c.reading
  return (
    <Stack gap={2} miw={160}>
      <Progress value={Math.min(100, c.load_pct)} color={TONE[c.state]} size="lg" radius="sm"
        aria-label={t('power.loadOf', { amps: r.amps, rating: c.rating_a, pct: c.load_pct })} />
      <Text size="xs">{t('power.loadOf', { amps: r.amps, rating: c.rating_a, pct: c.load_pct })}</Text>
      <Text size="xs" c="dimmed">
        {r.source === 'plugin' ? t('power.readFrom', { plugin: r.plugin, ago: ago(r.at, t) }) : t('power.readBy', { who: r.by ?? '?', ago: ago(r.at, t) })}
      </Text>
    </Stack>
  )
}

function Feeds({ c }: { c: Circuit }) {
  const { t } = useTranslation()
  const parts = [c.feeds_label, ...c.fed.switches.map((s) => s.name)].filter(Boolean)
  if (!parts.length) return <Text size="sm" c="dimmed">{t('power.nothingFed')}</Text>
  return (
    <Stack gap={0}>
      <Text size="sm">{parts.join(', ')}</Text>
      {c.fed.seats.length > 0 && <Text size="xs" c="dimmed">{t('power.seats', { count: c.fed.seats.length })}</Text>}
    </Stack>
  )
}

function BoardCard({ board, circuits, data, busy, onEditBoard, onRemoveBoard, onEdit, onRemove, onReading, onTrip }: {
  board: PowerBoard
  circuits: Circuit[]
  data: PowerOverview
  busy: boolean
  onEditBoard: () => void
  onRemoveBoard: () => void
  onEdit: (c: Circuit) => void
  onRemove: (c: Circuit) => void
  onReading: (c: Circuit) => void
  onTrip: (c: Circuit, tripped: boolean) => void
}) {
  const { t } = useTranslation()
  return (
    <Paper withBorder radius="lg" p="md" component="section" aria-labelledby={`board-${board.id}`}>
      <Group justify="space-between" mb="xs">
        <div>
          <Title order={2} size="h4" id={`board-${board.id}`}>
            <IconBolt size={18} style={{ verticalAlign: '-3px' }} aria-hidden="true" /> {board.name}
          </Title>
          {board.location && <Text size="sm" c="dimmed">{board.location}</Text>}
        </div>
        {data.can_edit && (
          <Group gap="xs">
            <Button size="xs" variant="default" onClick={onEditBoard}>{t('power.edit')}</Button>
            {!circuits.length && <Button size="xs" variant="subtle" color="down" onClick={onRemoveBoard}>{t('power.remove')}</Button>}
          </Group>
        )}
      </Group>
      {!circuits.length ? (
        <Text c="dimmed" size="sm">{t('power.noCircuits')}</Text>
      ) : (
        <Table.ScrollContainer minWidth={760}>
          <Table verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('power.circuit')}</Table.Th>
                <Table.Th>{t('power.load')}</Table.Th>
                <Table.Th>{t('power.feeds')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {circuits.map((c) => (
                <Table.Tr key={c.id} data-circuit={c.id}>
                  <Table.Td>
                    <Text fw={600} size="sm">{c.name}</Text>
                    <Group gap={4} mt={2}>
                      <Badge size="sm" color={TONE[c.state]} variant={c.state === 'ok' || c.state === 'unknown' ? 'light' : 'filled'}>
                        {t(`power.state.${c.state}`)}
                      </Badge>
                      <Badge size="sm" variant="outline" color="gray">{c.phase} · {c.rating_a} A</Badge>
                    </Group>
                  </Table.Td>
                  <Table.Td><Load c={c} /></Table.Td>
                  <Table.Td><Feeds c={c} /></Table.Td>
                  <Table.Td>
                    <Group gap={6} justify="flex-end" wrap="nowrap">
                      {data.can_read && (
                        <>
                          <Button size="xs" variant="default" onClick={() => onReading(c)} disabled={busy}>{t('power.enterReading')}</Button>
                          {c.tripped
                            ? <Button size="xs" color="up" onClick={() => onTrip(c, false)} disabled={busy}>{t('power.backOn')}</Button>
                            : <Button size="xs" color="down" variant="light" onClick={() => onTrip(c, true)} disabled={busy}>{t('power.tripped')}</Button>}
                        </>
                      )}
                      {data.can_edit && (
                        <>
                          <Button size="xs" variant="subtle" onClick={() => onEdit(c)}>{t('power.edit')}</Button>
                          <Button size="xs" variant="subtle" color="down" onClick={() => onRemove(c)}>{t('power.remove')}</Button>
                        </>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Paper>
  )
}

type Editing = { kind: 'board'; board: PowerBoard | null } | { kind: 'circuit'; circuit: Circuit | null } | null

/** Electrics: distribution boards, their circuits and the load on each (issue #45). */
export default function Power() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const power = usePower()
  const canCheck = useCan('plugins.run')
  const switches = useQuery({ queryKey: qk.switches, queryFn: () => get<{ id: string; name: string }[]>('/api/switches') })
  const [editing, setEditing] = useState<Editing>(null)
  const [reading, setReading] = useState<Circuit | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const refresh = () => void client.invalidateQueries({ queryKey: qk.power })
  useLiveEvent('power.changed', refresh)

  const close = () => { setEditing(null); setReading(null); setDialogError(null) }
  const saved = { onSuccess: () => { close(); refresh() }, onError: (e: Error) => setDialogError(e.message) }
  const saveBoard = useMutation({
    mutationFn: (v: { id?: string; body: unknown }) => (v.id ? patch(`/api/power/boards/${v.id}`, v.body) : post('/api/power/boards', v.body)),
    ...saved,
  })
  const saveCircuit = useMutation({
    mutationFn: (v: { id?: string; body: unknown }) => (v.id ? patch(`/api/power/circuits/${v.id}`, v.body) : post('/api/power/circuits', v.body)),
    ...saved,
  })
  const saveReading = useMutation({
    mutationFn: (v: { id: string; body: unknown }) => post(`/api/power/circuits/${v.id}/reading`, v.body),
    ...saved,
  })
  const act = useMutation({
    mutationFn: (v: { path: string; method: 'post' | 'del'; body?: unknown }) => (v.method === 'del' ? del(v.path) : post(v.path, v.body)),
    onSuccess: refresh,
  })
  const check = useMutation({
    mutationFn: () => post<PowerOverview>('/api/power/check'),
    onSuccess: (d) => client.setQueryData(qk.power, (old: PowerOverview | undefined) => ({ ...d, can_edit: old?.can_edit ?? false, can_read: old?.can_read ?? false })),
  })
  const data = power.data
  const error = power.error ?? act.error ?? check.error

  return (
    <Layout title={t('power.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead
        title={t('power.title')}
        desc={data ? t('power.intro', { warn: data.warn, crit: data.crit }) : undefined}
        actions={data?.enabled && (
          <Group gap="xs">
            {canCheck && data.plugins > 0 && (
              <Button variant="default" leftSection={<IconRefresh size={16} />} loading={check.isPending} onClick={() => check.mutate()}>
                {t('power.checkNow')}
              </Button>
            )}
            {data.can_edit && (
              <>
                <Button variant="default" leftSection={<IconPlus size={16} />} onClick={() => { setDialogError(null); setEditing({ kind: 'board', board: null }) }}>
                  {t('power.addBoard')}
                </Button>
                {data.boards.length > 0 && (
                  <Button leftSection={<IconPlus size={16} />} onClick={() => { setDialogError(null); setEditing({ kind: 'circuit', circuit: null }) }}>
                    {t('power.addCircuit')}
                  </Button>
                )}
              </>
            )}
          </Group>
        )}
      />
      {error && <Alert color="down" role="alert" mb="md">{t('common.error', { message: error.message })}</Alert>}
      {power.isPending || !data ? (
        <Loader size="sm" />
      ) : !data.enabled ? (
        <Text c="dimmed">{t('power.off')}</Text>
      ) : (
        <Stack gap="md">
          {data.circuits.length > 0 && (
            <Group gap="xs" aria-live="polite">
              {ORDER.filter((s) => data.counts[s]).map((s) => (
                <Badge key={s} color={TONE[s]} variant={s === 'ok' || s === 'unknown' ? 'light' : 'filled'} size="lg" tt="none">
                  {t(`power.count.${s}`, { count: data.counts[s] })}
                </Badge>
              ))}
            </Group>
          )}
          {!data.boards.length && <Text c="dimmed">{t('power.noBoards')}</Text>}
          {data.boards.map((b) => (
            <BoardCard key={b.id} board={b} data={data} busy={act.isPending}
              circuits={data.circuits.filter((c) => c.board === b.id)}
              onEditBoard={() => { setDialogError(null); setEditing({ kind: 'board', board: b }) }}
              onRemoveBoard={() => { if (window.confirm(t('power.removeBoardConfirm', { name: b.name }))) act.mutate({ path: `/api/power/boards/${b.id}`, method: 'del' }) }}
              onEdit={(c) => { setDialogError(null); setEditing({ kind: 'circuit', circuit: c }) }}
              onRemove={(c) => { if (window.confirm(t('power.removeCircuitConfirm', { name: c.name }))) act.mutate({ path: `/api/power/circuits/${c.id}`, method: 'del' }) }}
              onReading={(c) => { setDialogError(null); setReading(c) }}
              onTrip={(c, tripped) => act.mutate({ path: `/api/power/circuits/${c.id}/trip`, method: 'post', body: { tripped } })} />
          ))}
          <BoardDialog open={editing?.kind === 'board'} board={editing?.kind === 'board' ? editing.board : null}
            busy={saveBoard.isPending} error={dialogError} onClose={close}
            onSave={(body) => saveBoard.mutate({ id: editing?.kind === 'board' ? editing.board?.id : undefined, body })} />
          <CircuitDialog open={editing?.kind === 'circuit'} circuit={editing?.kind === 'circuit' ? editing.circuit : null}
            overview={data} switches={switches.data ?? []} busy={saveCircuit.isPending} error={dialogError} onClose={close}
            onSave={(body) => saveCircuit.mutate({ id: editing?.kind === 'circuit' ? editing.circuit?.id : undefined, body })} />
          <ReadingDialog circuit={reading} busy={saveReading.isPending} error={dialogError} onClose={close}
            onSave={(body) => reading && saveReading.mutate({ id: reading.id, body })} />
        </Stack>
      )}
    </Layout>
  )
}
