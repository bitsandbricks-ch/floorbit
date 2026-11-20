import { Group, Paper, SegmentedControl, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get } from '@/api/client'
import { qk } from '@/api/keys'
import { ErrorBanner, LoadingState } from '@/components/ui'
import { TimeChart, type TimePoint } from '@/widgets/TimeChart'

/** GET /api/wifi/history: clients on the controllers that stream to Telemetry (floorbit/wifi.py). */
export interface WifiHistoryData { controllers: string[]; points: TimePoint[]; hours: number }

const RANGES = ['1', '6', '24'] as const

/** Clients over time. Only a controller streaming to Telemetry has a history: a plugin is asked live. */
export function WifiHistory() {
  const { t, i18n } = useTranslation()
  const [hours, setHours] = useState<string>('6')
  const q = useQuery({
    queryKey: qk.wifiHistory(hours),
    queryFn: () => get<WifiHistoryData>(`/api/wifi/history?hours=${hours}`),
    refetchInterval: 60_000,
  })
  const until = Math.floor(q.dataUpdatedAt / 1000)
  const since = until - Number(hours) * 3600
  const num = (v: number) => Math.round(v).toLocaleString(i18n.language)
  return (
    <Paper withBorder radius="lg" p="md">
      <Group justify="space-between" wrap="wrap" mb="xs">
        <Title order={2} size="h4">{t('wifi.history')}</Title>
        <SegmentedControl size="xs" value={hours} onChange={setHours} aria-label={t('wifi.historyRange')}
          data={RANGES.map((h) => ({ value: h, label: t('wifi.historyHours', { count: Number(h) }) }))} />
      </Group>
      <ErrorBanner error={q.error} />
      {q.isPending ? <LoadingState /> : !q.data || q.data.points.length === 0 ? (
        <Text size="sm" c="dimmed">{t('wifi.historyNone')}</Text>
      ) : (
        <>
          <TimeChart points={q.data.points} since={since} until={until} label={t('wifi.history')}
            format={(v) => t('wifi.historyMax', { n: num(v) })} />
          <Text size="xs" c="dimmed" mt="xs">{t('wifi.historyFrom', { controllers: q.data.controllers.join(', ') })}</Text>
        </>
      )}
    </Paper>
  )
}
