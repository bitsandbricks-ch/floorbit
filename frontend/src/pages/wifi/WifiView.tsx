import {
  Alert, Anchor, Badge, Group, Paper, SegmentedControl, Select, Stack, Text, Title,
} from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { WifiAp, WifiBand, WifiData, WifiRadio } from '@/api/types'
import type { ViewProps } from '@/pages/monitoring/pages'
import { type DataColumn, DataTable, ErrorBanner, LoadingState, StatTile } from '@bitsandbricks/ui'
import { channelColor, loadColor } from './colors'
import { blockTop } from '@/pages/plan/blockTop'
import { WifiHistory } from './WifiHistory'

const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/wifi.md'
const RADIUS = 80   // an AP's circle on the plan, in plan units
type Mode = 'load' | 'clients' | 'channels'

function radioOn(ap: WifiAp, band: WifiBand): WifiRadio | undefined {
  return ap.radios.find((r) => r.band === band)
}

function Plan({ data, band, mode, label }: { data: WifiData; band: WifiBand; mode: Mode; label: string }) {
  const drawing = data.drawing!
  const crowded = data.thresholds.crowded
  const clash = new Set(data.overlaps.filter((o) => o.band === band).flatMap((o) => o.aps))
  const aps = data.aps.filter((a) => a.on_plan)
  const colorOf = (ap: WifiAp) => {
    const r = radioOn(ap, band)
    if (ap.status === 'down' || !r) return 'var(--color-muted)'
    if (mode === 'channels') return channelColor(r.channel)
    if (mode === 'clients') return loadColor(Math.min(100, (r.clients / crowded) * 100), 100)
    return loadColor(r.utilization, data.thresholds.busy)
  }
  const valueOf = (ap: WifiAp) => {
    const r = radioOn(ap, band)
    if (ap.status === 'down') return '✕'
    if (!r) return '–'
    if (mode === 'channels') return String(r.channel ?? '?')
    if (mode === 'clients') return String(r.clients)
    return r.utilization == null ? '?' : `${r.utilization}%`
  }
  return (
    <svg viewBox={drawing.box} role="img" aria-label={label} className="fb-wifi-plan">
      <defs>
        {aps.map((ap, i) => (
          <radialGradient key={ap.name} id={`wifi-heat-${i}`}>
            <stop offset="0%" style={{ stopColor: colorOf(ap), stopOpacity: 0.55 }} />
            <stop offset="100%" style={{ stopColor: colorOf(ap), stopOpacity: 0 }} />
          </radialGradient>
        ))}
      </defs>
      {drawing.shapes.map((b, i) => (
        <g key={i}>
          <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
            {b.cells.map((c) => (
              <rect key={c.seat} className="cell" x={c.x + 1} y={c.y + 1} width={drawing.cell - 2} height={drawing.cell - 2} rx={3} />
            ))}
          </g>
          {b.name && <text className="name" x={b.cx} y={blockTop(b) - 12}>{b.name}</text>}
        </g>
      ))}
      {aps.map((ap, i) => ap.status === 'up' && radioOn(ap, band) && (
        <circle key={ap.name} cx={ap.px!} cy={ap.py!} r={RADIUS * 2.2} fill={`url(#wifi-heat-${i})`} className="heat" />
      ))}
      {aps.map((ap) => (
        <g key={ap.name} data-ap={ap.name}>
          {clash.has(ap.name) && <circle className="clash" cx={ap.px!} cy={ap.py!} r={34} />}
          <circle className={ap.status === 'down' ? 'ap down' : 'ap'} cx={ap.px!} cy={ap.py!} r={24} style={{ fill: colorOf(ap) }}>
            <title>{ap.name}</title>
          </circle>
          <text className="val" x={ap.px!} y={ap.py! + 8}>{valueOf(ap)}</text>
          <text className="ap-name" x={ap.px!} y={ap.py! + 58}>{ap.name}</text>
        </g>
      ))}
    </svg>
  )
}

/** Access point load, clients per AP and channels on the floor plan (issue #98). Counts only. */
export default function WifiView({ expanded }: ViewProps) {
  const { t, i18n } = useTranslation()
  const [hall, setHall] = useState<string | null>(null)
  const query = useQuery({
    queryKey: qk.wifi(hall ?? ''),
    queryFn: () => get<WifiData>(`/api/wifi${hall ? `?hall=${encodeURIComponent(hall)}` : ''}`),
    refetchInterval: 30_000,
  })
  const d = query.data
  const bands = (['2.4', '5', '6'] as WifiBand[]).filter((b) => d?.bands[b])
  const [pickedBand, setBand] = useState<WifiBand | null>(null)
  const band = pickedBand && bands.includes(pickedBand) ? pickedBand : (bands.includes('5') ? '5' : bands[0] ?? '5')
  const [mode, setMode] = useState<Mode>('load')
  const num = (n: number) => n.toLocaleString(i18n.language)
  const unplaced = d?.aps.filter((a) => !a.placed).length ?? 0

  return (
    <>
      {expanded && d && d.halls.length > 1 && (
        <Group justify="flex-end" mb="sm">
          <Select aria-label={t('wifi.hall')} value={d.hall} onChange={setHall} allowDeselect={false} w={200}
            data={d.halls.map((h) => ({ value: h.id, label: h.name }))} />
        </Group>
      )}
      <Stack gap="md">
        <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        {d?.errors.map((e) => <Alert key={e} color="warn">{t('wifi.pluginError', { message: e })}</Alert>)}
        {query.isPending || !d ? <LoadingState rows={3} /> : d.sources.length === 0 ? (
          <Alert color="gray" variant="light">{t('wifi.noPlugin')} <Anchor href={DOCS}>docs/wifi.md</Anchor></Alert>
        ) : (
          <>
            <div className="fb-stat-row">
              <StatTile label={t('wifi.clients')} value={num(d.clients)}
                sub={bands.map((b) => t('wifi.bandClients', { band: b, count: d.bands[b]!.clients })).join(' · ')} />
              <StatTile label={t('wifi.aps')} value={`${d.up} / ${d.aps.length}`} tone={d.down.length ? 'err' : 'ok'}
                sub={d.down.length ? t('wifi.down', { names: d.down.join(', ') }) : t('wifi.allUp')} />
              <StatTile label={t('wifi.busy')} value={num(d.busy.length)} tone={d.busy.length ? 'warn' : undefined}
                sub={d.busy.join(', ') || t('wifi.busyNone', { pct: d.thresholds.busy })} />
              <StatTile label={t('wifi.overlaps')} value={num(d.overlaps.length)} tone={d.overlaps.length ? 'warn' : undefined} sub={t('wifi.overlapsSub')} />
            </div>
            {!expanded ? null : d.drawing && d.aps.some((a) => a.on_plan) ? (
              <Paper withBorder radius="lg" p="md">
                <Group justify="space-between" mb="sm" wrap="wrap">
                  <SegmentedControl value={mode} onChange={(v) => setMode(v as Mode)} aria-label={t('wifi.show')}
                    data={(['load', 'clients', 'channels'] as Mode[]).map((m) => ({ value: m, label: t(`wifi.mode.${m}`) }))} />
                  {bands.length > 1 && (
                    <SegmentedControl value={band} onChange={(v) => setBand(v as WifiBand)} aria-label={t('wifi.band')}
                      data={bands.map((b) => ({ value: b, label: `${b} GHz` }))} />
                  )}
                </Group>
                <Plan data={d} band={band} mode={mode} label={t('wifi.planLabel', { band })} />
                <Text size="xs" c="dimmed" mt="xs">
                  {mode === 'channels' ? t('wifi.keyChannels') : mode === 'clients'
                    ? t('wifi.keyClients', { count: d.thresholds.crowded }) : t('wifi.keyLoad', { pct: d.thresholds.busy })}
                </Text>
              </Paper>
            ) : (
              <Alert color="gray" variant="light">{t('wifi.notPlaced')}</Alert>
            )}
            {expanded && d.history && <WifiHistory />}
            {expanded && d.overlaps.length > 0 && (
              <Alert color="warn" title={t('wifi.overlapTitle')}>
                {d.overlaps.map((o) => (
                  <Text key={`${o.band}-${o.channel}-${o.aps.join()}`} size="sm">
                    {t('wifi.overlap', { a: o.aps[0], b: o.aps[1], band: o.band, channel: o.channel })}
                  </Text>
                ))}
              </Alert>
            )}
            {expanded && <Paper withBorder radius="lg" p="md">
              <Title order={2} size="h4" mb="xs">{t('wifi.list')}</Title>
              <DataTable rows={d.aps} rowKey={(ap) => ap.name} label={t('wifi.list')} urlState={false} pageSize={0} bare striped cards
                defaultSort={{ id: 'ap' }}
                columns={[
                  { id: 'ap', header: t('wifi.ap'), card: 'inline', sort: (ap) => ap.name, cell: (ap) => (
                    <>
                      <Group gap={6} wrap="wrap">
                        <Text fw={600} size="sm">{ap.name}</Text>
                        {ap.status === 'down' && <Badge color="down" variant="light" tt="none">{t('wifi.offline')}</Badge>}
                        {ap.busy && <Badge color="warn" variant="light" tt="none">{t('wifi.busyBadge')}</Badge>}
                        {!ap.placed && <Badge color="gray" variant="light" tt="none">{t('wifi.unplaced')}</Badge>}
                      </Group>
                      {ap.model && <Text size="xs" c="dimmed">{ap.model}</Text>}
                    </>
                  ) },
                  { id: 'clients', header: t('wifi.clients'), card: 'label', numeric: true, descFirst: true,
                    sort: (ap) => (ap.status === 'up' ? ap.clients : -1), cell: (ap) => (ap.status === 'up' ? num(ap.clients) : '–') },
                  ...bands.map((b): DataColumn<WifiAp> => ({ id: `band-${b}`, header: `${b} GHz`, card: 'label', descFirst: true,
                    sort: (ap) => radioOn(ap, b)?.utilization ?? -1, cell: (ap) => {
                      const r = radioOn(ap, b)
                      return r ? (
                        <Text size="sm">
                          {t('wifi.radio', { channel: r.channel ?? '?', width: r.width ?? '?', count: r.clients })}{' '}
                          {r.utilization != null && <Text span fw={600} style={{ color: loadColor(r.utilization, d.thresholds.busy) }}>{r.utilization}%</Text>}
                        </Text>
                      ) : '–'
                    } })),
                ]} />
              {unplaced > 0 && <Text size="xs" c="dimmed" mt="xs">{t('wifi.unplacedHint', { count: unplaced })}</Text>}
            </Paper>}
            {expanded && <Text size="xs" c="dimmed">{t('wifi.privacy', { sources: d.sources.join(', ') })}</Text>}
          </>
        )}
      </Stack>
    </>
  )
}
