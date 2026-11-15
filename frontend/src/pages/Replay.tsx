import { ActionIcon, Alert, Group, Loader, Paper, SegmentedControl, Select, SimpleGrid, Slider, Stack, Text, Title } from '@mantine/core'
import { IconPlayerPauseFilled, IconPlayerPlayFilled, IconPlayerSkipBack } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { EventReplayData, ReplayData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { EventReplay } from './replay/EventReplay'
import { openAt, sampleAt, seatsAt, SPEEDS, when } from './replay/model'
import { Chart, Plan } from './replay/Plan'
import { bps } from './stats/format'

const TICK = 200   // ms between steps while playing

export default function Replay() {
  const { t } = useTranslation()
  const [hall, setHall] = useState('')
  const [range, setRange] = useState<'day' | 'event'>('day')
  const hallArg = hall ? `?hall=${encodeURIComponent(hall)}` : ''
  const query = useQuery({ queryKey: qk.replay(hall), queryFn: () => get<ReplayData>(`/api/replay${hallArg}`), enabled: range === 'day' })
  const eventQuery = useQuery({
    queryKey: qk.replayEvent(hall), queryFn: () => get<EventReplayData>(`/api/replay/event${hallArg}`), enabled: range === 'event',
  })
  const data = query.data
  const shown = range === 'day' ? data : eventQuery.data
  const [at, setAt] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<string>(String(SPEEDS[1]))
  const [source, setSource] = useState<'ports' | 'checkins'>('ports')
  const start = data?.start ?? 0
  const end = data?.end ?? 0
  const time = at ?? start

  useEffect(() => {
    if (!playing || !data?.start) return
    const id = window.setInterval(() => {
      setAt((cur) => {
        const next = (cur ?? start) + (Number(speed) * TICK) / 1000
        if (next >= end) {
          setPlaying(false)
          return end
        }
        return next
      })
    }, TICK)
    return () => window.clearInterval(id)
  }, [playing, speed, start, end, data?.start])

  const on = useMemo(() => {
    if (!data) return new Set<string>()
    return source === 'checkins' ? seatsAt([], data.checkins, time) : seatsAt(data.seat_base.online, data.seat_events, time)
  }, [data, source, time])
  const open = useMemo(() => (data ? openAt(data.incidents, time) : []), [data, time])
  const rings = useMemo(() => new Set(open.map((i) => i.seat).filter((s): s is string => !!s)), [open])
  const sample = data ? sampleAt(data.samples, time) : null
  const seats = data?.drawing?.shapes.reduce((n, b) => n + b.cells.length, 0) ?? 0
  const here = data?.drawing ? new Set(data.drawing.shapes.flatMap((b) => b.cells.map((c) => c.seat))) : new Set<string>()
  const onHere = [...on].filter((s) => here.has(s)).length

  return (
    <Layout title={t('replay.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('replay.title')} desc={t('replay.intro')}
        actions={(
          <Group gap="sm">
            <SegmentedControl value={range} aria-label={t('replay.range')}
              onChange={(v) => { setRange(v as 'day' | 'event'); setPlaying(false) }}
              data={[{ value: 'day', label: t('replay.day') }, { value: 'event', label: t('replay.wholeEvent') }]} />
            {shown && shown.halls.length > 1 && (
              <Select aria-label={t('replay.hall')} value={shown.hall} allowDeselect={false}
                data={shown.halls.map((h) => ({ value: h.id, label: h.name }))}
                onChange={(v) => { setHall(v ?? ''); setAt(null); setPlaying(false) }} />
            )}
          </Group>
        )} />
      {range === 'event' ? (
        eventQuery.isPending ? <Loader aria-label={t('common.loading')} />
          : eventQuery.error ? <Alert color="down" role="alert">{t('common.error', { message: eventQuery.error.message })}</Alert>
            : !eventQuery.data?.frames.length ? <Paper withBorder radius="lg" p="lg"><Text c="dimmed">{t('replay.event.empty')}</Text></Paper>
              : <EventReplay key={eventQuery.data.hall} data={eventQuery.data} />
      ) : query.isPending ? (
        <Loader aria-label={t('common.loading')} />
      ) : query.error ? (
        <Alert color="down" role="alert">{t('common.error', { message: query.error.message })}</Alert>
      ) : !data?.start ? (
        <Paper withBorder radius="lg" p="lg"><Text c="dimmed">{t('replay.empty', { minutes: Math.round((data?.interval ?? 120) / 60) })}</Text></Paper>
      ) : (
        <Stack gap="md">
          <Paper withBorder radius="lg" p="md">
            <Group gap="sm" wrap="nowrap" align="center">
              <ActionIcon size="lg" variant="default" aria-label={t('replay.restart')} onClick={() => { setAt(start); setPlaying(false) }}>
                <IconPlayerSkipBack size={18} />
              </ActionIcon>
              <ActionIcon size="lg" aria-label={playing ? t('replay.pause') : t('replay.play')}
                onClick={() => { if (!playing && time >= end) setAt(start); setPlaying(!playing) }}>
                {playing ? <IconPlayerPauseFilled size={18} /> : <IconPlayerPlayFilled size={18} />}
              </ActionIcon>
              <Slider style={{ flex: 1 }} min={start} max={end} step={data.interval || 60} value={time} label={when}
                onChange={(v) => { setAt(v); setPlaying(false) }} thumbLabel={t('replay.time')} />
            </Group>
            <Group justify="space-between" mt="sm" gap="sm">
              <Title order={2} size="h3" aria-live="polite">{when(time)}</Title>
              <Group gap="sm">
                <SegmentedControl size="xs" value={speed} onChange={setSpeed} aria-label={t('replay.speed')}
                  data={SPEEDS.map((s) => ({ value: String(s), label: t(`replay.speed${s}`) }))} />
                {data.checkins.length > 0 && (
                  <SegmentedControl size="xs" value={source} onChange={(v) => setSource(v as 'ports' | 'checkins')} aria-label={t('replay.source')}
                    data={[{ value: 'ports', label: t('replay.ports') }, { value: 'checkins', label: t('replay.checkins') }]} />
                )}
              </Group>
            </Group>
          </Paper>

          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            <Paper withBorder radius="lg" p="sm"><Text size="xs" c="dimmed">{source === 'checkins' ? t('replay.checkedIn') : t('replay.online')}</Text><Text fw={700} size="xl">{t('replay.ofSeats', { on: onHere, total: seats })}</Text></Paper>
            <Paper withBorder radius="lg" p="sm"><Text size="xs" c="dimmed">{t('replay.bandwidth')}</Text><Text fw={700} size="xl">{sample ? bps(sample.down + sample.up) : '–'}</Text></Paper>
            <Paper withBorder radius="lg" p="sm"><Text size="xs" c="dimmed">{t('replay.peak')}</Text><Text fw={700} size="xl">{data.peak ? bps(data.peak.bps) : '–'}</Text>{data.peak && <Text size="xs" c="dimmed">{when(data.peak.at)}</Text>}</Paper>
            <Paper withBorder radius="lg" p="sm"><Text size="xs" c="dimmed">{t('replay.incidents')}</Text><Text fw={700} size="xl">{open.length}</Text></Paper>
          </SimpleGrid>

          {data.samples.length > 1 && (
            <Paper withBorder radius="lg" p="md">
              <Text size="sm" fw={600} mb={6}>{t('replay.chart')}</Text>
              <Chart samples={data.samples} peak={data.peak} start={start} end={end} t={time} onSeek={(v) => { setAt(v); setPlaying(false) }} label={t('replay.chartLabel')} />
            </Paper>
          )}

          <Paper withBorder radius="lg" p="md">
            {data.drawing ? <Plan drawing={data.drawing} on={on} rings={rings} label={t('replay.planLabel', { time: when(time) })} />
              : <Text c="dimmed">{t('replay.noPlan')}</Text>}
            <Group gap="md" mt="xs">
              <Text size="xs" c="dimmed"><span className="fb-replay-key on" /> {source === 'checkins' ? t('replay.checkedIn') : t('replay.online')}</Text>
              <Text size="xs" c="dimmed"><span className="fb-replay-key ring" /> {t('replay.openIncident')}</Text>
            </Group>
          </Paper>

          {open.length > 0 && (
            <Paper withBorder radius="lg" p="md">
              <Text size="sm" fw={600} mb={6}>{t('replay.openAt')}</Text>
              <Stack gap={4}>
                {open.map((i) => (
                  <Text key={i.id} size="sm">{i.seat ?? i.switch ?? ''} · {i.title} <Text span c="dimmed" size="xs">({when(i.start)})</Text></Text>
                ))}
              </Stack>
            </Paper>
          )}
          <Text size="xs" c="dimmed">{t('replay.kept')} {t('replay.keptEvent')}</Text>
        </Stack>
      )}
    </Layout>
  )
}
