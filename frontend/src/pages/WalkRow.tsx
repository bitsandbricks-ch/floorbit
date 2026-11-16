import { Alert, Autocomplete, Badge, Button, Group, Loader, Paper, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { IconPlugConnected } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError, get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useCan } from '@/api/queries'
import type { BlockPlan, CableList, SeatAssigned, SeatBlock, WalkUp, WalkWatch } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'

type Setup = { block: string; switch: string; order: string }

/** The walk itself: one seat at a time, and the port that just came up. */
function Walk({ setup, seats, onStop }: { setup: Setup; seats: string[]; onStop: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useCan('floorplan.edit')
  const [at, setAt] = useState(0)
  const [switchName, setSwitchName] = useState(setup.switch)
  const [since, setSince] = useState(0)            // the server's clock: 0 until the first answer
  const [used, setUsed] = useState<string[]>([])   // ports already given to a seat or skipped in this walk
  const [found, setFound] = useState<Record<string, string>>({})
  const [clash, setClash] = useState<{ port: string; other: string } | null>(null)
  const cables = useQuery({ queryKey: qk.cables, queryFn: () => get<CableList>('/api/cables') })
  const watch = useQuery({
    queryKey: qk.walk(switchName, since),
    queryFn: async () => {
      const answer = await get<WalkWatch>(`/api/cables/walk?switch=${encodeURIComponent(switchName)}${since ? `&since=${since}` : ''}`)
      if (!since) setSince(answer.since)
      return answer
    },
    enabled: Boolean(switchName.trim()),
    refetchInterval: 2000,
  })
  const seat = seats[at]
  const fresh: WalkUp | undefined = watch.data?.ups.find((u) => !used.includes(u.port))
  const known = cables.data?.cables.find((c) => c.seat === seat && c.source !== 'import')
  const next = () => { setClash(null); setAt((n) => n + 1) }
  const assign = useMutation({
    mutationFn: ({ port, swap }: { port: string; swap?: boolean }) =>
      post<SeatAssigned>('/api/cables/assign', { seat, switch: switchName, port, swap, block: setup.block }),
    onSuccess: (_r, { port }) => {
      setUsed((u) => [...u, port]); setFound((f) => ({ ...f, [seat]: port }))
      void qc.invalidateQueries({ queryKey: qk.cables }); next()
    },
    onError: (e, { port }) => {
      if (e instanceof ApiError && e.status === 409 && e.data.other_seat) setClash({ port, other: String(e.data.other_seat) })
    },
  })
  const restart = (name: string) => { setSwitchName(name); setSince(0); setUsed([]) }
  const done = Object.keys(found).length
  if (!seat) {
    return (
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="sm">
          <Title order={2} size="h3">{t('walk.finished', { count: done, seats: seats.length })}</Title>
          <Button variant="default" onClick={onStop}>{t('walk.again')}</Button>
        </Stack>
      </Paper>
    )
  }
  return (
    <Stack gap="md">
      <Paper withBorder radius="lg" p="lg">
        <Stack gap="xs">
          <Group justify="space-between">
            <Text size="sm" c="dimmed">{t('walk.progress', { n: at + 1, of: seats.length, done })}</Text>
            <Button size="compact-sm" variant="subtle" onClick={onStop}>{t('walk.stop')}</Button>
          </Group>
          <Title order={2} size="h1">{seat}</Title>
          <Text>{t('walk.plugIn', { seat })}</Text>
          <Text size="sm" c="dimmed">
            {known ? t('walk.known', { port: `${known.switch} ${known.port}` }) : t('walk.unknown')}
          </Text>
        </Stack>
      </Paper>
      <Paper withBorder radius="lg" p="lg" aria-live="polite">
        {fresh ? (
          <Stack gap="sm">
            <Group gap="xs">
              <IconPlugConnected size={20} />
              <Text fw={600}>{t('walk.cameUp', { port: `${switchName} ${fresh.port}` })}</Text>
              {fresh.how === 'poll' && <Badge variant="light" color="info" tt="none">{t('walk.byPoll')}</Badge>}
            </Group>
            {clash ? (
              <>
                <Alert color="warn">{t('walk.clash', { port: clash.port, other: clash.other, seat })}</Alert>
                <Stack gap="xs">
                  <Button size="md" loading={assign.isPending} onClick={() => assign.mutate({ port: clash.port, swap: true })}>
                    {t('walk.swap', { seat, other: clash.other })}</Button>
                  <Button variant="default" onClick={() => setClash(null)}>{t('walk.cancel')}</Button>
                </Stack>
              </>
            ) : (
              <Group grow>
                <Button size="md" disabled={!canEdit} loading={assign.isPending} onClick={() => assign.mutate({ port: fresh.port })}>
                  {t('walk.thatsIt', { seat })}</Button>
                <Button size="md" variant="default" onClick={() => setUsed((u) => [...u, fresh.port])}>{t('walk.notIt')}</Button>
              </Group>
            )}
            {assign.error && !clash && <Alert color="down" role="alert">{assign.error.message}</Alert>}
          </Stack>
        ) : (
          <Group gap="sm">
            <Loader size="sm" type="dots" />
            <Text>{t('walk.waiting', { switch: switchName })}</Text>
          </Group>
        )}
      </Paper>
      <Group grow>
        <Button variant="default" disabled={at === 0} onClick={() => { setClash(null); setAt((n) => n - 1) }}>{t('walk.back')}</Button>
        <Button variant="default" onClick={next}>{t('walk.skip')}</Button>
      </Group>
      <Autocomplete label={t('walk.switch')} data={[switchName]} value={switchName} onChange={restart}
        description={t('walk.switchHint')} />
      {watch.data && (
        <Text size="sm" c="dimmed">{watch.data.syslog ? t('walk.bySyslog') : t('walk.noSyslog')}</Text>
      )}
      {watch.error && <Alert color="down" role="alert">{watch.error.message}</Alert>}
    </Stack>
  )
}

/** Walking the row (issue #473): plug in at each seat in turn and Floorbit names the port that came up. */
export default function WalkRow() {
  const { t } = useTranslation()
  const blocks = useQuery({ queryKey: qk.seatBlocks, queryFn: () => get<SeatBlock[]>('/api/seat-blocks') })
  const switches = useQuery({ queryKey: qk.switches, queryFn: () => get<{ id: string; name: string }[]>('/api/switches') })
  const [setup, setSetup] = useState<Setup>({ block: '', switch: '', order: 'rows' })
  const [walking, setWalking] = useState(false)
  const ready = Boolean(setup.block && setup.switch.trim())
  // The block's seats in walking order, as the block patch plan numbers them; the ports are not used.
  const order = useQuery({
    queryKey: qk.walkOrder(setup),
    queryFn: () => post<BlockPlan>('/api/cables/block', { ...setup, first_port: 'Gi1/0/1', dry_run: true }),
    enabled: ready, retry: false,
  })
  const seats = (order.data?.cables ?? []).map((c) => c.seat)
  const set = (k: keyof Setup) => (v: string | null) => setSetup((s) => ({ ...s, [k]: v ?? '' }))
  return (
    <Layout title={t('walk.title')} back={{ href: '/cables', label: t('cables.title') }}>
      {/* On a phone in the row, the seat comes first: the intro only before the walk. */}
      <PageHead title={t('walk.title')} desc={walking ? undefined : t('walk.intro')} />
      {walking && seats.length ? <Walk setup={setup} seats={seats} onStop={() => setWalking(false)} /> : (
        <Paper withBorder radius="lg" p="lg">
          <Stack gap="sm">
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
              <Select label={t('cables.block')} required searchable value={setup.block || null} onChange={set('block')}
                data={(blocks.data ?? []).map((b) => ({ value: b.id, label: `${b.name || '–'} (${b.cols * b.rows})` }))} />
              <Autocomplete label={t('cables.switch')} required value={setup.switch} onChange={set('switch')}
                data={(switches.data ?? []).map((s) => s.name)} />
              <Select label={t('cables.order')} allowDeselect={false} value={setup.order} onChange={set('order')}
                data={[{ value: 'rows', label: t('cables.orderRows') }, { value: 'snake', label: t('cables.orderSnake') }]} />
            </SimpleGrid>
            {order.error && <Alert color="down" role="alert">{order.error.message}</Alert>}
            <Button disabled={!seats.length} onClick={() => setWalking(true)}>
              {seats.length ? t('walk.start', { count: seats.length }) : t('walk.pick')}
            </Button>
          </Stack>
        </Paper>
      )}
    </Layout>
  )
}
