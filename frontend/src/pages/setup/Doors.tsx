import { Badge, Button, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { IconPlayerPlay, IconPrinter } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { PreflightBoard, PreflightGroupId, PreflightStatus } from '@/api/types'
import { Panel } from '@/components/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import { when } from '../handover/format'

const COLOR: Record<PreflightStatus, string> = { pass: 'up', warn: 'warn', fail: 'down', skip: 'gray' }
const GROUPS: PreflightGroupId[] = ['switches', 'uplinks', 'services']
/** How often the open page asks for fresh answers; the server re-runs only what is over a minute old. */
const EVERY_MS = 60_000

/** Before doors open (#1049): switches reachable, uplinks up, DHCP and DNS answering. The checks run
 *  by themselves while the page is open; "Check now" asks again at once. Passes fold into one line,
 *  so what still fails is what the crew reads. */
export function DoorsCheck() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canRun = useCan('incidents.work')
  const query = useQuery({
    queryKey: qk.preflight,
    queryFn: () => post<PreflightBoard>('/api/preflight/refresh'),
    refetchInterval: EVERY_MS,
  })
  useLiveEvent('preflight.changed', () => void qc.invalidateQueries({ queryKey: qk.preflight }))
  const run = useMutation({
    mutationFn: () => post<PreflightBoard>('/api/preflight/run', {}),
    onSuccess: (b) => qc.setQueryData(qk.preflight, b),
  })
  const b = query.data
  const verdict = !b ? null : b.ready ? 'ready' : b.complete ? 'notReady' : 'incomplete'

  return (
    <Panel id="doors" title={t('preflight.title')} desc={t('preflight.intro')}
      actions={
        <>
          <Button size="compact-sm" variant="default" component="a" target="_blank"
            href={`/api/preflight.pdf?tz=${new Date().getTimezoneOffset()}`} leftSection={<IconPrinter size={14} />}>
            {t('preflight.print')}
          </Button>
          {canRun && (
            <Button size="compact-sm" variant="default" loading={run.isPending} onClick={() => run.mutate()}
              leftSection={<IconPlayerPlay size={14} />}>
              {t('preflight.checkNow')}
            </Button>
          )}
        </>
      }>
      <ErrorBanner error={query.error ?? run.error} mb="sm" />
      {query.isPending ? <LoadingState rows={3} /> : b && (
        <Stack gap="md">
          <Group gap={6}>
            <Text fw={700} mr="xs" c={b.ready ? 'up' : b.complete ? 'down' : undefined}>{t(`preflight.verdict.${verdict}`)}</Text>
            {(['pass', 'warn', 'fail', 'skip'] as const).filter((s) => b.counts[s] > 0 || s === 'fail').map((s) => (
              <Badge key={s} variant="light" color={COLOR[s]} tt="none">{t(`preflight.count.${s}`, { count: b.counts[s] })}</Badge>
            ))}
          </Group>
          <SimpleGrid cols={{ base: 1, md: 3 }} spacing="lg">
            {GROUPS.map((g) => {
              const group = b.groups[g]
              const open = group?.items.filter((i) => i.status !== 'pass') ?? []
              const passed = (group?.items.length ?? 0) - open.length
              return (
                <Stack key={g} gap={6} data-group={g}>
                  <div>
                    <Title order={3} size="h5">{t(`preflight.group.${g}`)}</Title>
                    <Text size="xs" c="dimmed">
                      {group ? t('preflight.checked', { when: when(group.at), who: group.by ?? t('preflight.byFloorbit') }) : t('preflight.notRun')}
                    </Text>
                  </div>
                  {open.map((i) => (
                    <Group key={i.id} gap="sm" wrap="nowrap" align="flex-start">
                      <Badge variant="filled" color={COLOR[i.status]} miw={64} tt="none" style={{ flexShrink: 0 }}>{t(`preflight.status.${i.status}`)}</Badge>
                      <Stack gap={0} style={{ minWidth: 0 }}>
                        <Text size="sm" fw={600} style={{ overflowWrap: 'anywhere' }}>{i.name}</Text>
                        {i.detail && <Text size="xs" c="dimmed">{i.detail}</Text>}
                      </Stack>
                    </Group>
                  ))}
                  {passed > 0 && (
                    <Group gap="sm" wrap="nowrap">
                      <Badge variant="light" color="up" miw={64} tt="none" style={{ flexShrink: 0 }}>{t('preflight.status.pass')}</Badge>
                      <Text size="sm" c="dimmed">{t(open.length ? 'preflight.restOk' : 'preflight.allOk', { count: passed })}</Text>
                    </Group>
                  )}
                </Stack>
              )
            })}
          </SimpleGrid>
        </Stack>
      )}
    </Panel>
  )
}
