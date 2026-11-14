import { ActionIcon, Alert, Group, Loader, Paper, SegmentedControl, Select, SimpleGrid, Slider, Stack, Text, Title } from '@mantine/core'
import { IconPlayerPauseFilled, IconPlayerPlayFilled, IconPlayerSkipBack } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { PlanDrawing, ReplayData } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { chartPath, openAt, sampleAt, seatsAt, SPEEDS, when } from './replay/model'
import { bps } from './stats/format'

const TICK = 200   // ms between steps while playing
const CHART_W = 1000
const CHART_H = 120

function Plan({ drawing, on, rings, label }: { drawing: PlanDrawing; on: Set<string>; rings: Set<string>; label: string }) {
  return (
    <svg viewBox={drawing.box} role="img" aria-label={label} className="fb-replay-plan">
      {drawing.shapes.map((b, i) => (
        <g key={i}>
          <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
            <rect className="blk" x={-b.w / 2 - 6} y={-b.h / 2 - 6} width={b.w + 12} height={b.h + 12} rx={6} />
            {b.cells.map((c) => (
              <g key={c.seat}>
                <rect className={on.has(c.seat) ? 'cell on' : 'cell'} data-seat={c.seat} x={c.x + 1} y={c.y + 1}
                  width={drawing.cell - 2} height={drawing.cell - 2} rx={3}>
                  <title>{c.seat}</title>
                </rect>
                {rings.has(c.seat) && <circle className="ring" cx={c.x + drawing.cell / 2} cy={c.y + drawing.cell / 2} r={drawing.cell * 0.9} />}
              </g>
            ))}
          </g>
          {b.name && <text className="name" x={b.cx} y={b.cy - Math.max(b.w, b.h) / 2 - 18}>{b.name}</text>}
        </g>
      ))}
    </svg>
  )
}

function Chart({ data, start, end, t, onSeek, label }: {
  data: ReplayData; start: number; end: number; t: number; onSeek: (t: number) => void; label: string
}) {
  const span = Math.max(1, end - start)
  const x = (ts: number) => ((ts - start) / span) * CHART_W
  const line = chartPath(data, start, end, CHART_W, CHART_H)
  return (
    <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} preserveAspectRatio="none" className="fb-replay-chart" role="img" aria-label={label}
      onClick={(e) => {
        const box = e.currentTarget.getBoundingClientRect()
        onSeek(start + ((e.clientX - box.left) / box.width) * span)
      }}>
      {line && <path d={`${line} L${CHART_W},${CHART_H} L0,${CHART_H} Z`} className="area" />}
      {line && <path d={line} className="line" />}
      {data.peak && data.peak.at >= start && <line className="peak" x1={x(data.peak.at)} x2={x(data.peak.at)} y1={0} y2={CHART_H} />}
      <line className="cursor" x1={x(t)} x2={x(t)} y1={0} y2={CHART_H} />
    </svg>
  )
}

export default function Replay() {
  const { t } = useTranslation()
  const [hall, setHall] = useState('')
  const query = useQuery({ queryKey: qk.replay(hall), queryFn: () => get<ReplayData>(`/api/replay${hall ? `?hall=${encodeURIComponent(hall)}` : ''}`) })
  const data = query.data
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
        actions={data && data.halls.length > 1 && (
          <Select aria-label={t('replay.hall')} value={data.hall} allowDeselect={false}
            data={data.halls.map((h) => ({ value: h.id, label: h.name }))}
            onChange={(v) => { setHall(v ?? ''); setAt(null); setPlaying(false) }} />
        )} />
      {query.isPending ? (
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
              <Chart data={data} start={start} end={end} t={time} onSeek={(v) => { setAt(v); setPlaying(false) }} label={t('replay.chartLabel')} />
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
          <Text size="xs" c="dimmed">{t('replay.kept')}</Text>
        </Stack>
      )}
    </Layout>
  )
}
