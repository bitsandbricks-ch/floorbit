import { ActionIcon, Button, Group, SegmentedControl, SimpleGrid, Slider, Stack, Text, Title } from '@mantine/core'
import { IconDownload, IconPlayerPauseFilled, IconPlayerPlayFilled, IconPlayerSkipBack } from '@tabler/icons-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { EventReplayData } from '@/api/types'
import { StatCard } from '@/components/StatCard'
import { Panel } from '@/components/ui'
import { bps } from '../stats/format'
import { heatmap, sampleAt, when, type HeatMetric } from './model'
import { Chart, Plan } from './Plan'

const TICK = 200
const EVENT_SPEEDS = [900, 3600, 14400] as const
const METRICS: HeatMetric[] = ['online', 'traffic', 'incidents']
const CELL_W = 10
const ROW_H = 22
const LABEL_W = 56

function Heatmap({ data, metric, t, onSeek, label }: {
  data: EventReplayData; metric: HeatMetric; t: number; onSeek: (t: number) => void; label: string
}) {
  const { names, cols } = useMemo(() => heatmap(data.frames, metric), [data.frames, metric])
  const { t: tr } = useTranslation()
  if (!names.length) return <Text size="sm" c="dimmed">{tr('replay.event.noBlocks')}</Text>
  const w = LABEL_W + cols.length * CELL_W
  const h = names.length * ROW_H
  const at = cols.findIndex((c) => t >= c.t && t <= c.end + 1)
  const fmt = (v: number) => (metric === 'online' ? `${Math.round(v * 100)} %` : metric === 'traffic' ? bps(v) : String(v))
  return (
    <div className="fb-heatmap-scroll">
    <svg viewBox={`0 0 ${w} ${h}`} className={`fb-heatmap ${metric}`} role="img" aria-label={label}>
      {names.map((n, r) => (
        <g key={n}>
          <text x={LABEL_W - 8} y={r * ROW_H + ROW_H / 2 + 4} className="label">{n}</text>
          {cols.map((c, i) => (
            <rect key={c.t} x={LABEL_W + i * CELL_W} y={r * ROW_H + 1} width={CELL_W - 1} height={ROW_H - 2}
              style={{ fillOpacity: 0.08 + c.values[r] * 0.92 }} onClick={() => onSeek(c.t)}>
              <title>{`${n} · ${when(c.t)} · ${fmt(c.raw[r])}`}</title>
            </rect>
          ))}
        </g>
      ))}
      {at >= 0 && <rect className="cursor" x={LABEL_W + at * CELL_W - 1} y={0} width={CELL_W + 1} height={h} />}
    </svg>
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
  const time = at ?? start

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
  const on = useMemo(() => new Set(frame?.seats ?? []), [frame])
  const rings = useMemo(() => new Set(frame?.incidents ?? []), [frame])
  const peak = useMemo(() => frames.reduce<{ bps: number; at: number } | null>(
    (best, f) => (!best || f.down + f.up > best.bps ? { bps: f.down + f.up, at: f.t } : best), null), [frames])
  const seats = data.drawing?.shapes.reduce((n, b) => n + b.cells.length, 0) ?? 0
  const seek = (v: number) => { setAt(v); setPlaying(false) }

  return (
    <Stack gap="md">
      <Panel>
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
      </Panel>

      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        <StatCard label={t('replay.online')} value={t('replay.ofSeats', { on: on.size, total: seats })} />
        <StatCard label={t('replay.bandwidth')} value={frame ? bps(frame.down + frame.up) : '–'} />
        <StatCard label={t('replay.peak')} value={peak ? bps(peak.bps) : '–'} sub={peak ? when(peak.at) : undefined} />
        <StatCard label={t('replay.incidents')} value={String(rings.size)} />
      </SimpleGrid>

      <Panel>
        {data.drawing ? <Plan drawing={data.drawing} on={on} rings={rings} label={t('replay.planLabel', { time: when(time) })} />
          : <Text c="dimmed">{t('replay.noPlan')}</Text>}
        <Group gap="md" mt="xs">
          <Text size="xs" c="dimmed"><span className="fb-replay-key on" /> {t('replay.online')}</Text>
          <Text size="xs" c="dimmed"><span className="fb-replay-key ring" /> {t('replay.openIncident')}</Text>
        </Group>
      </Panel>

      {frames.length > 1 && (
        <Panel title={t('replay.chart')}>
          <Chart samples={frames} peak={peak} start={start} end={end} t={time} onSeek={seek} label={t('replay.chartLabel')} />
        </Panel>
      )}

      <Panel title={t('replay.event.heatmap')} actions={
        <SegmentedControl size="xs" value={metric} onChange={(v) => setMetric(v as HeatMetric)} aria-label={t('replay.event.metric')}
          data={METRICS.map((m) => ({ value: m, label: t(`replay.event.${m}`) }))} />
      }>
        <Heatmap data={data} metric={metric} t={time} onSeek={seek} label={t('replay.event.heatmapLabel', { metric: t(`replay.event.${metric}`) })} />
      </Panel>

      <Panel title={t('replay.event.export')}>
        <Group gap="sm">
          <Button component="a" href="/api/replay/event.json" download variant="default" leftSection={<IconDownload size={16} />}>
            {t('replay.event.json')}
          </Button>
        </Group>
        <Text size="xs" c="dimmed" mt="xs">{t('replay.event.exportHint')}</Text>
      </Panel>
      <Text size="xs" c="dimmed">{t('replay.event.kept')}</Text>
    </Stack>
  )
}
