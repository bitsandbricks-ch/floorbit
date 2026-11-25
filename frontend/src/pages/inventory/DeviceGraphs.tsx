import { Group, SegmentedControl, Select, SimpleGrid, Text } from '@mantine/core'
import { IconChartLine } from '@tabler/icons-react'
import { useQueries } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import type { DeviceInterface } from '@/api/types'
import { TimeChart, type TimePoint } from '@bitsandbricks/widgets'
import { stats } from '@/components/timeSeries'
import { Panel } from '@/components/ui'
import { EmptyState, ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { BITS, scaled } from '@/lib/units'

/** GET /api/telemetry/series (floorbit/telemetry/storage.py): one series, oldest first. */
interface Series { points: TimePoint[] }

const RANGES = ['1', '6', '24', '48'] as const
const DEVICE = ['cpu', 'mem', 'up'] as const
const PORT = ['in_bps', 'out_bps', 'errors'] as const
type Metric = (typeof DEVICE)[number] | (typeof PORT)[number]

/** One device's numbers over time (issue #903): load and reachability, then one port's traffic.
 *  A metric nothing was stored for is left out. */
export function DeviceGraphs({ name, interfaces }: { name: string; interfaces: DeviceInterface[] }) {
  const { t, i18n } = useTranslation()
  const [hours, setHours] = useState<string>('6')
  const ports = interfaces.filter((i) => !i.hidden && i.name).map((i) => i.name)
  const [port, setPort] = useState<string | null>(ports[0] ?? null)
  const asks: { metric: Metric; port: string | null }[] = [
    ...DEVICE.map((metric) => ({ metric, port: null })),
    ...(port ? PORT.map((metric) => ({ metric, port })) : []),
  ]
  const results = useQueries({
    queries: asks.map((a) => ({
      queryKey: qk.telemetrySeries(name, a.port ?? '', a.metric, hours),
      queryFn: () => get<Series>(`/api/telemetry/series?${new URLSearchParams({ device: name, metric: a.metric, hours, ...(a.port ? { port: a.port } : {}) })}`),
      refetchInterval: 60_000,
    })),
  })
  const until = Math.floor(Math.max(0, ...results.map((r) => r.dataUpdatedAt)) / 1000)
  const since = until - Number(hours) * 3600
  const num = (v: number) => v.toLocaleString(i18n.language, { maximumFractionDigits: v < 10 ? 1 : 0 })
  const write = (m: Metric) => (v: number) => {
    if (m === 'in_bps' || m === 'out_bps') return scaled(v, BITS, i18n.language).join(' ')
    if (m === 'cpu' || m === 'mem') return `${num(v)} %`
    if (m === 'up') return t(v >= 0.5 ? 'deviceTabs.graphs.upYes' : 'deviceTabs.graphs.upNo')
    return num(v)
  }
  const shown = asks.map((a, i) => ({ ...a, points: results[i].data?.points ?? [] }))
  const chart = ({ metric, port: p, points }: (typeof shown)[number]) => {
    const label = p ? t(`deviceTabs.graphs.metric.${metric}`, { port: p }) : t(`deviceTabs.graphs.metric.${metric}`)
    const value = write(metric)
    const s = stats(points)
    return (
      <Panel key={`${metric}-${p ?? ''}`} title={label} desc={points.length ? value(points[points.length - 1][1]) : undefined}>
        {points.length ? (
          <>
            <TimeChart points={points} since={since} until={until} label={label} value={value}
              format={metric === 'up'
                ? () => t('deviceTabs.graphs.upShare', { pct: Math.round(s.avg * 100) })
                : (v) => t('deviceTabs.graphs.max', { value: value(v) })} />
            {metric !== 'up' && (
              <Text size="xs" c="dimmed" mt={4} style={{ fontVariantNumeric: 'tabular-nums' }}>
                {t('deviceTabs.graphs.stats', { min: value(s.min), avg: value(s.avg), max: value(s.max) })}
              </Text>
            )}
          </>
        ) : <Text size="sm" c="dimmed">{t('deviceTabs.graphs.noPoints')}</Text>}
      </Panel>
    )
  }
  const pending = results.some((r) => r.isPending)
  const error = results.find((r) => r.error)?.error ?? null
  const devicePanels = shown.filter((s) => !s.port && s.points.length)
  return (
    <>
      <Group justify="space-between" wrap="wrap" mb="sm">
        <Text size="sm" c="dimmed">{t('deviceTabs.graphs.help')}</Text>
        <SegmentedControl size="xs" value={hours} onChange={setHours} aria-label={t('deviceTabs.graphs.range')}
          data={RANGES.map((h) => ({ value: h, label: t('deviceTabs.graphs.hours', { count: Number(h) }) }))} />
      </Group>
      <ErrorBanner error={error} />
      {pending ? <LoadingState rows={3} /> : (
        <>
          {devicePanels.length === 0 ? (
            <Panel><EmptyState icon={<IconChartLine size={24} />} title={t('deviceTabs.graphs.noneTitle')} description={t('deviceTabs.graphs.none')} /></Panel>
          ) : (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">{devicePanels.map(chart)}</SimpleGrid>
          )}
          {ports.length > 0 && (
            <>
              <Group mt="lg" mb="sm" gap="sm">
                <Text fw={600} size="sm">{t('deviceTabs.graphs.port')}</Text>
                <Select size="xs" w={200} searchable allowDeselect={false} aria-label={t('deviceTabs.graphs.port')}
                  value={port} onChange={setPort} data={ports} />
              </Group>
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">{shown.filter((s) => s.port).map(chart)}</SimpleGrid>
            </>
          )}
        </>
      )}
    </>
  )
}
