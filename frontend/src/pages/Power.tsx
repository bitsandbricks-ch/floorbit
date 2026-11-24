import { Anchor, Badge, Button, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core'
import { IconBolt, IconPlus, IconRefresh } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan, usePower } from '@/api/queries'
import type { PowerOverview } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { ErrorBanner } from '@bitsandbricks/ui'
import { CircuitTable } from './power/parts'
import { boardPath, ORDER, TONE } from './power/state'

/** Electrics: distribution boards, their circuits and the load on each (issue #45). Every board
 *  and circuit opens its own page, where it is changed and readings are typed in (issue #877). */
export default function Power() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const power = usePower()
  const canCheck = useCan('plugins.run')
  useLiveEvent('power.changed', () => void client.invalidateQueries({ queryKey: qk.power }))
  const check = useMutation({
    mutationFn: () => post<PowerOverview>('/api/power/check'),
    onSuccess: (d) => client.setQueryData(qk.power, (old: PowerOverview | undefined) => ({ ...d, can_edit: old?.can_edit ?? false, can_read: old?.can_read ?? false })),
  })
  const data = power.data

  return (
    // Circuits getting close, about to trip or tripped show in a background tab (issue #218).
    <Layout title={t('power.title')}
      count={data ? (data.counts.warn ?? 0) + (data.counts.crit ?? 0) + (data.counts.tripped ?? 0) : undefined}>
      <PageHead
        title={t('power.title')}
        desc={data ? t('power.intro', { warn: data.warn, crit: data.crit }) : undefined}
        actions={data?.enabled && (
          <Group gap="xs">
            {canCheck && data.plugins > 0 && (
              <Button variant="default" leftSection={<IconRefresh size={16} />} loading={check.isPending} onClick={() => check.mutate()}>
                {t('power.checkNow')}
              </Button>
            )}
            {data.can_edit && (
              <>
                <Button variant="default" leftSection={<IconPlus size={16} />} component={Link} to={boardPath('new')}>
                  {t('power.addBoard')}
                </Button>
                {data.boards.length > 0 && (
                  <Button leftSection={<IconPlus size={16} />} component={Link} to="/power/circuits/new">{t('power.addCircuit')}</Button>
                )}
              </>
            )}
          </Group>
        )}
      />
      <ErrorBanner error={power.error ?? check.error} mb="md" />
      {power.isPending || !data ? (
        <Loader size="sm" />
      ) : !data.enabled ? (
        <Text c="dimmed">{t('power.off')}</Text>
      ) : (
        <Stack gap="md">
          {data.circuits.length > 0 && (
            <Group gap="xs" aria-live="polite">
              {ORDER.filter((s) => data.counts[s]).map((s) => (
                <Badge key={s} color={TONE[s]} variant={s === 'ok' || s === 'unknown' ? 'light' : 'filled'} size="lg" tt="none">
                  {t(`power.count.${s}`, { count: data.counts[s] })}
                </Badge>
              ))}
            </Group>
          )}
          {!data.boards.length && <Text c="dimmed">{t('power.noBoards')}</Text>}
          {data.boards.map((b) => {
            const circuits = data.circuits.filter((c) => c.board === b.id)
            return (
              <Paper key={b.id} withBorder p="md" component="section" aria-labelledby={`board-${b.id}`}>
                <Group gap="xs" mb="xs" align="baseline">
                  <Title order={2} size="h4" id={`board-${b.id}`}>
                    <IconBolt size={18} style={{ verticalAlign: '-3px' }} aria-hidden="true" />{' '}
                    <Anchor component={Link} to={boardPath(b.id)} inherit c="inherit">{b.name}</Anchor>
                  </Title>
                  {b.location && <Text size="sm" c="dimmed">{b.location}</Text>}
                </Group>
                {circuits.length ? <CircuitTable circuits={circuits} /> : <Text c="dimmed" size="sm">{t('power.noCircuits')}</Text>}
              </Paper>
            )
          })}
        </Stack>
      )}
    </Layout>
  )
}
