import { Alert, Anchor, Badge, Button, Group, Stack, Text } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { del, post } from '@/api/client'
import type { CheckinLookup, LookupWindow as Window } from '@/api/types'
import { ErrorBanner, Panel } from '@/components/ui'
import { dayClock } from '@/lib/time'

/** When check-ins may ask the switches for their PC (docs/segments.md): open from doors open for a
 *  few hours, or by hand. */
export function LookupWindow({ w, canEdit, onChange }: { w: Window; canEdit: boolean; onChange: () => void }) {
  const { t } = useTranslation()
  const change = useMutation({
    mutationFn: (open: boolean) => (open ? post('/api/checkins/lookup-window', {}) : del('/api/checkins/lookup-window')),
    onSuccess: onChange,
  })
  return (
    <Panel title={t('crewCheckin.lookups.title')} desc={t('crewCheckin.lookups.intro', { hours: w.hours })}
      actions={canEdit && (w.open
        ? w.why === 'by_hand' && <Button variant="default" loading={change.isPending} onClick={() => change.mutate(false)}>
            {t('crewCheckin.lookups.close')}</Button>
        : <Button variant="default" loading={change.isPending} onClick={() => change.mutate(true)}>
            {t('crewCheckin.lookups.openNow', { hours: w.hours })}</Button>)}>
      <Stack gap="xs">
        <ErrorBanner error={change.error} />
        <Group gap="xs">
          <Badge color={w.open ? 'up' : 'gray'} variant="light" tt="none">
            {w.open && w.until ? t('crewCheckin.lookups.open', { until: dayClock(w.until) }) : t('crewCheckin.lookups.closed')}
          </Badge>
          {w.open && w.why && <Text size="sm" c="dimmed">{t(`crewCheckin.lookups.openWhy.${w.why}`)}</Text>}
        </Group>
        {w.segments_on === 0 && (
          <Alert color="warn" role="status">
            {t('crewCheckin.lookups.noSegments')}{' '}
            <Anchor component={Link} to="/telemetry?tab=segments">{t('crewCheckin.lookups.segments')}</Anchor>
          </Alert>
        )}
      </Stack>
    </Panel>
  )
}

/** One check-in's lookup in a line for the crew: a to-do when it couldn't ask. */
export function LookupNote({ lookup: l }: { lookup: CheckinLookup | null | undefined }) {
  const { t } = useTranslation()
  if (!l) return null
  const text = l.state === 'todo' && l.todo ? t(`crewCheckin.lookups.todo.${l.todo}`, { vlan: l.vlan })
    : l.state === 'closed' || l.state === 'error' || l.state === 'not_found' ? t(`crewCheckin.lookups.state.${l.state}`)
      : null
  return text ? <Text size="xs" c="dimmed">{text}</Text> : null
}
