import { ActionIcon, Button, Group, SegmentedControl, SimpleGrid, Slider, Stack, Text, Title } from '@mantine/core'
import { IconDownload, IconPlayerPauseFilled, IconPlayerPlayFilled, IconPlayerSkipBack } from '@tabler/icons-react'
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import type { EventReplayData } from '@/api/types'
import { Card, StatTile } from '@bitsandbricks/ui'
import { bps } from '../stats/format'
import { heatmap, sampleAt, when, type HeatMetric } from './model'
import { Chart, Plan } from './Plan'
import './EventReplay.css'

const TICK = 200
const EVENT_SPEEDS = [900, 3600, 14400] as const
const METRICS: HeatMetric[] = ['online', 'traffic', 'incidents']

function Heatmap({ data, metric, t, onSeek, label }: {
  data: EventReplayData; metric: HeatMetric; t: number; onSeek: (t: number) => void; label: string
}) {
  const { names, cols } = useMemo(() => heatmap(data.frames, metric), [data.frames, metric])
  const { t: tr } = useTranslation()
  if (!names.length) return <Text size="sm" c="dimmed">{tr('replay.event.noBlocks')}</Text>
  const at = cols.findIndex((c) => t >= c.t && t <= c.end + 1)
  const fmt = (v: number) => (metric === 'online' ? `${Math.round(v * 100)} %` : metric === 'traffic' ? bps(v) : String(v))
  // Plain boxes, not an SVG scaled to the width: with only a few frames the scaling blew the
  // block names and the cursor up to the whole page (#1432).
  return (
    <div className={`fb-heatmap ${metric}`} role="img" aria-label={label}>
      {names.map((n, r) => (
        <div key={n} className="row">
          <span className="label">{n}</span>
          {cols.map((c, i) => (
            <span key={c.t} className={`cell${i === at ? ' at' : ''}`} style={{ '--v': `${Math.round(8 + c.values[r] * 92)}%` } as CSSProperties}
              title={`${n} · ${when(c.t)} · ${fmt(c.raw[r])}`} onClick={() => onSeek(c.t)} />
          ))}
        </div>
      ))}
    </div>
  )
}

/** The whole event (issue #104): the recording's frames on the plan, a block heatmap, and exports. */
export function EventReplay({ data }: { data: EventReplayData }) {
  const { t } = useTranslation()
  const frames = data.frames
  const start = data.start ?? 0
  const end = data.end ?? 0
  const [at, setAt] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<string>(String(EVENT_SPEEDS[1]))
  const [metric, setMetric] = useState<HeatMetric>('online')
  // Opens on the latest frame, as the clock says (#1432); Play starts over from the beginning.
  const time = at ?? end

  useEffect(() => {
    if (!playing) return
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
  }, [playing, speed, start, end])

  const frame = sampleAt(frames, time)
  const peak = useMemo(() => frames.reduce<{ bps: number; at: number } | null>(
    (best, f) => (!best || f.down + f.up > best.bps ? { bps: f.down + f.up, at: f.t } : best), null), [frames])
  const seats = data.drawing?.shapes.reduce((n, b) => n + b.cells.length, 0) ?? 0
  const seek = (v: number) => { setAt(v); setPlaying(false) }

  return (
    <Stack gap="md">
      <Card heading={2}>
        <Group gap="sm" wrap="nowrap" align="center">
          <ActionIcon size="lg" variant="default" aria-label={t('replay.restart')} onClick={() => seek(start)}>
            <IconPlayerSkipBack size={18} />
          </ActionIcon>
          <ActionIcon size="lg" aria-label={playing ? t('replay.pause') : t('replay.play')}
            onClick={() => { if (!playing && time >= end) setAt(start); setPlaying(!playing) }}>
            {playing ? <IconPlayerPauseFilled size={18} /> : <IconPlayerPlayFilled size={18} />}
          </ActionIcon>
          <Slider style={{ flex: 1 }} min={start} max={Math.max(end, start + 1)} step={data.step} value={time} label={when}
            onChange={seek} thumbLabel={t('replay.time')} />
        </Group>
        <Group justify="space-between" mt="sm" gap="sm">
          <Title order={2} size="h3" aria-live="polite">{when(time)}</Title>
          <SegmentedControl size="xs" value={speed} onChange={setSpeed} aria-label={t('replay.speed')}
            data={EVENT_SPEEDS.map((s) => ({ value: String(s), label: t(`replay.speed${s}`) }))} />
        </Group>
      </Card>

      <div className="fb-replay-body">
        <Card heading={2} className="fb-replay-plan-box">
          {data.drawing ? <Plan hall={data.hall} drawing={data.drawing} frame={frame} label={t('replay.planLabel', { time: when(time) })} />
            : <Text c="dimmed">{t('replay.noPlan')}</Text>}
        </Card>
        <Stack gap="md" className="fb-replay-side">
          <SimpleGrid cols={2} spacing="md">
            <StatTile label={t('replay.online')} value={t('replay.ofSeats', { on: frame?.seats.length ?? 0, total: seats })} />
            <StatTile label={t('replay.bandwidth')} value={frame ? bps(frame.down + frame.up) : '–'} />
            <StatTile label={t('replay.peak')} value={peak ? bps(peak.bps) : '–'} sub={peak ? when(peak.at) : undefined} />
            <StatTile label={t('replay.incidents')} value={String(frame?.incidents.length ?? 0)} />
          </SimpleGrid>
          {frames.length > 1 && (
            <Card heading={2} title={t('replay.chart')}>
              <Chart samples={frames} peak={peak} start={start} end={end} t={time} onSeek={seek} label={t('replay.chartLabel')} />
            </Card>
          )}
        </Stack>
      </div>

      <Card heading={2} title={t('replay.event.heatmap')} actions={
        <SegmentedControl size="xs" value={metric} onChange={(v) => setMetric(v as HeatMetric)} aria-label={t('replay.event.metric')}
          data={METRICS.map((m) => ({ value: m, label: t(`replay.event.${m}`) }))} />
      }>
        <Heatmap data={data} metric={metric} t={time} onSeek={seek} label={t('replay.event.heatmapLabel', { metric: t(`replay.event.${metric}`) })} />
      </Card>

      <Card heading={2} title={t('replay.event.export')}>
        <Group gap="sm">
          <Button component="a" href="/api/replay/event.json" download variant="default" leftSection={<IconDownload size={16} />}>
            {t('replay.event.json')}
          </Button>
        </Group>
        <Text size="xs" c="dimmed" mt="xs">{t('replay.event.exportHint')}</Text>
      </Card>
      <Text size="xs" c="dimmed">{t('replay.event.kept')}</Text>
    </Stack>
  )
}
