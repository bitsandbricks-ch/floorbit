import { ActionIcon, Group, Modal, SegmentedControl, SimpleGrid, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { Panel } from '@/components/ui'
import { EmptyState, ErrorBanner, LoadingState, type Widget } from '@bitsandbricks/ui'
import { FitWidget, type TimePoint } from '@bitsandbricks/widgets'
import { IconArrowsMaximize, IconChartLine } from '@tabler/icons-react'
import { HoverTimeChart } from '@/components/HoverTimeChart'
import { stats } from '@/components/timeSeries'
import './AgentGraphs.css'

/** GET /api/agents/<id>/history (floorbit/agent_history.py): rates are per minute. */
export interface AgentHistory { hours: number; series: Record<string, TimePoint[]> }

// The page's order: is telemetry flowing, does it reach Floorbit, then the agent's own link.
const METRICS = ['points', 'sent', 'series', 'heard', 'failing', 'telegraf_restarts', 'reconnects', 'syslog', 'median_ms'] as const
const RANGES = ['1', '6', '24', '48'] as const
const PER_MINUTE: readonly string[] = ['points', 'sent', 'reconnects', 'syslog']

/** One agent's numbers over time: each one's latest value as the dashboards' stat widget (#1321),
 *  then its chart; a metric it never sent is left out. */
export function AgentGraphs({ agentId }: { agentId: string }) {
  const { t, i18n } = useTranslation()
  const [hours, setHours] = useState<string>('6')
  const [big, setBig] = useState<(typeof METRICS)[number] | null>(null)
  const q = useQuery({
    queryKey: [...qk.agents, agentId, 'history', hours],
    queryFn: () => get<AgentHistory>(`/api/agents/${agentId}/history?hours=${hours}`),
    refetchInterval: 60_000,
  })
  const until = Math.floor(q.dataUpdatedAt / 1000)     // when the numbers were read: 0 only before they are
  const since = until - Number(hours) * 3600
  const shown = METRICS.filter((m) => (q.data?.series[m] ?? []).length > 0)
  const num = (v: number) => v.toLocaleString(i18n.language, { maximumFractionDigits: v < 10 ? 1 : 0 })
  const unit = (m: string) => PER_MINUTE.includes(m) ? t('agents.graphs.unit.perMinute') : m === 'median_ms' ? t('agents.graphs.unit.ms') : ''
  const widget = (m: string, pts: TimePoint[]): Widget => ({ type: 'series', id: m, label: t(`agents.graphs.metric.${m}`),
    size: 'small', refresh: 60, sub: '', link: '', unit: unit(m), series: [{ label: t(`agents.graphs.metric.${m}`), points: pts }] })

  return (
    <>
      <Group justify="space-between" wrap="wrap" mb="sm">
        <Text size="sm" c="dimmed">{t('agents.graphs.help')}</Text>
        <SegmentedControl size="xs" value={hours} onChange={setHours} aria-label={t('agents.graphs.range')}
          data={RANGES.map((h) => ({ value: h, label: t('agents.graphs.hours', { count: Number(h) }) }))} />
      </Group>
      <ErrorBanner error={q.error} />
      {q.isPending ? <LoadingState rows={3} /> : shown.length === 0 ? (
        <Panel><EmptyState icon={<IconChartLine size={24} />} title={t('agents.graphs.noneTitle')} description={t('agents.graphs.none')} /></Panel>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {shown.map((m) => {
            const pts = q.data!.series[m]
            const s = stats(pts)
            const name = t(`agents.graphs.metric.${m}`)
            return (
              <Panel key={m} title={name} desc={t(`agents.graphs.note.${m}`)}
                actions={<ActionIcon variant="subtle" color="gray" aria-label={t('agents.graphs.bigger', { name })} onClick={() => setBig(m)}>
                  <IconArrowsMaximize size={16} />
                </ActionIcon>}>
                {/* The latest value as the stat widget, at the level without its own graph: the chart under it has the history. */}
                <div className="fb-agent-stat"><FitWidget widget={widget(m, pts)} pick="stat" pin="m" /></div>
                <HoverTimeChart points={pts} since={since} until={until} label={name}
                  format={(v) => t('agents.graphs.max', { n: num(v) })} value={num} />
                <Text size="xs" c="dimmed" mt={4} style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {t('agents.graphs.stats', { min: num(s.min), avg: num(s.avg), max: num(s.max) })}
                </Text>
              </Panel>
            )
          })}
        </SimpleGrid>
      )}
      {/* One chart large, with the same range picker (issue #868). */}
      <Modal opened={!!big && !!q.data?.series[big]?.length} onClose={() => setBig(null)} size="xl"
        title={big ? t(`agents.graphs.metric.${big}`) : ''} closeButtonProps={{ 'aria-label': t('agents.graphs.close') }}>
        {big && q.data?.series[big]?.length ? (
          <>
            <SegmentedControl size="xs" mb="sm" value={hours} onChange={setHours} aria-label={t('agents.graphs.range')}
              data={RANGES.map((h) => ({ value: h, label: t('agents.graphs.hours', { count: Number(h) }) }))} />
            <HoverTimeChart points={q.data.series[big]} since={since} until={until} height={320} label={t(`agents.graphs.metric.${big}`)}
              format={(v) => t('agents.graphs.max', { n: num(v) })} value={num} />
            <Text size="sm" c="dimmed" mt={4} style={{ fontVariantNumeric: 'tabular-nums' }}>
              {(({ min, avg, max }) => t('agents.graphs.stats', { min: num(min), avg: num(avg), max: num(max) }))(stats(q.data.series[big]))}
            </Text>
          </>
        ) : null}
      </Modal>
    </>
  )
}
