import { Group, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { Problem } from '@/api/types'
import { ago, dateTime } from '@/lib/time'
import { StatusBadge } from '@bitsandbricks/ui'

/** A problem's facts: state, since when, where, and what it cuts off. */
export function ProblemFacts({ p }: { p: Problem }) {
  const { t } = useTranslation()
  return (
    <Stack gap={6}>
      <Group gap="sm" wrap="nowrap">
        <Text size="sm" c="dimmed" w={150} style={{ flexShrink: 0 }}>{t('problem.level')}</Text>
        <StatusBadge size="sm" state={p.muted ? 'unknown' : p.level === 'down' ? 'down' : 'warn'} label={t(`problem.levels.${p.muted ? 'muted' : p.level}`)} />
      </Group>
      <Row label={t('problem.since')} value={p.since ? `${dateTime(p.since)} (${ago(p.since)})` : t('problem.sinceUnknown')} />
      {p.device && <Row label={t('problem.switch')} value={p.device} />}
      {p.seat && <Row label={t('problem.seat')} value={p.seat} />}
      {p.cause && <Text size="sm" c="down">{t('problems.behindCause', { name: p.cause })}</Text>}
      {(p.seats?.length ?? 0) > 0 && <Row label={t('problem.cutOff')} value={p.seats!.join(', ')} />}
      {(p.behind?.length ?? 0) > 0 && <Row label={t('problem.behind')} value={p.behind!.join(', ')} />}
      {p.muted && <Text size="sm" c="dimmed">{t('problems.mutedUntil', { time: dateTime(p.muted.until), who: p.muted.by ?? '?' })}{p.muted.reason ? ` · ${p.muted.reason}` : ''}</Text>}
    </Stack>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Group gap="sm" wrap="nowrap" align="flex-start">
      <Text size="sm" c="dimmed" w={150} style={{ flexShrink: 0 }}>{label}</Text>
      <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{value}</Text>
    </Group>
  )
}
