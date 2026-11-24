import { Group, SegmentedControl, SimpleGrid, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { EmptyState, ErrorBanner, LoadingState, Panel } from '@/components/ui'
import { TimeChart, type TimePoint } from '@bitsandbricks/widgets'
import { IconChartLine } from '@tabler/icons-react'

/** GET /api/agents/<id>/history (floorbit/agent_history.py): rates are per minute. */
export interface AgentHistory { hours: number; series: Record<string, TimePoint[]> }

// The page's order: is telemetry flowing, does it reach Floorbit, then the agent's own link.
const METRICS = ['points', 'sent', 'series', 'heard', 'failing', 'telegraf_restarts', 'reconnects', 'syslog', 'median_ms'] as const
const RANGES = ['1', '6', '24', '48'] as const

/** One agent's numbers over time, a small chart each; a metric it never sent is left out. */
export function AgentGraphs({ agentId }: { agentId: string }) {
  const { t, i18n } = useTranslation()
  const [hours, setHours] = useState<string>('6')
  const q = useQuery({
    queryKey: [...qk.agents, agentId, 'history', hours],
    queryFn: () => get<AgentHistory>(`/api/agents/${agentId}/history?hours=${hours}`),
    refetchInterval: 60_000,
  })
  const until = Math.floor(q.dataUpdatedAt / 1000)     // when the numbers were read: 0 only before they are
  const since = until - Number(hours) * 3600
  const shown = METRICS.filter((m) => (q.data?.series[m] ?? []).length > 0)
  const num = (v: number) => v.toLocaleString(i18n.language, { maximumFractionDigits: v < 10 ? 1 : 0 })

  return (
    <>
      <Group justify="space-between" wrap="wrap" mb="sm">
        <Text size="sm" c="dimmed">{t('agents.graphs.help')}</Text>
        <SegmentedControl size="xs" value={hours} onChange={setHours} aria-label={t('agents.graphs.range')}
          data={RANGES.map((h) => ({ value: h, label: t('agents.graphs.hours', { count: Number(h) }) }))} />
      </Group>
      <ErrorBanner error={q.error} />
      {q.isPending ? <LoadingState /> : shown.length === 0 ? (
        <Panel><EmptyState icon={<IconChartLine size={24} />} title={t('agents.graphs.noneTitle')} desc={t('agents.graphs.none')} /></Panel>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {shown.map((m) => {
            const pts = q.data!.series[m]
            const last = pts[pts.length - 1][1]
            return (
              <Panel key={m} title={t(`agents.graphs.metric.${m}`)} desc={t(`agents.graphs.unit.${m}`, { n: num(last) })}>
                <TimeChart points={pts} since={since} until={until} format={(v) => t('agents.graphs.max', { n: num(v) })} label={t(`agents.graphs.metric.${m}`)} />
              </Panel>
            )
          })}
        </SimpleGrid>
      )}
    </>
  )
}
