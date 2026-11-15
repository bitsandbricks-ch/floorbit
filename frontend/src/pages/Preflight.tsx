import { Alert, Badge, Button, Group, Loader, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { IconPlayerPlay, IconPrinter } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get, post } from '@/api/client'
import { qk } from '@/api/keys'
import { useLiveEvent } from '@/api/live'
import { useCan } from '@/api/queries'
import type { PreflightBoard, PreflightGroupId, PreflightStatus } from '@/api/types'
import { Layout } from '@/components/Layout'
import { PageHead } from '@/components/PageHead'
import { when } from './handover/format'

const COLOR: Record<PreflightStatus, string> = { pass: 'up', warn: 'warn', fail: 'down', skip: 'gray' }
const GROUPS: PreflightGroupId[] = ['switches', 'uplinks', 'services']

/** Before doors open: switches reachable, uplinks up, DHCP and DNS answering. */
export default function Preflight() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canRun = useCan('incidents.work')
  const query = useQuery({ queryKey: qk.preflight, queryFn: () => get<PreflightBoard>('/api/preflight') })
  useLiveEvent('preflight.changed', () => void qc.invalidateQueries({ queryKey: qk.preflight }))
  const run = useMutation({
    mutationFn: (group?: PreflightGroupId) => post<PreflightBoard>('/api/preflight/run', group ? { group } : {}),
    onSuccess: (b) => qc.setQueryData(qk.preflight, b),
  })
  const b = query.data
  const busy = (g?: PreflightGroupId) => run.isPending && run.variables === g
  const verdict = !b ? null : b.ready ? 'ready' : b.complete ? 'notReady' : 'incomplete'

  return (
    <Layout title={t('preflight.title')} back={{ href: '/', label: t('common.floorPlan') }}>
      <PageHead title={t('preflight.title')} desc={t('preflight.intro')}
        actions={
          <>
            <Button variant="default" component="a" target="_blank"
              href={`/api/preflight.pdf?tz=${new Date().getTimezoneOffset()}`} leftSection={<IconPrinter size={16} />}>
              {t('preflight.print')}
            </Button>
            {canRun && (
              <Button loading={busy(undefined)} onClick={() => run.mutate(undefined)} leftSection={<IconPlayerPlay size={16} />}>
                {t('preflight.runAll')}
              </Button>
            )}
          </>
        } />
      <Stack gap="md">
        {(query.error ?? run.error) && <Alert color="down" role="alert">{t('common.error', { message: (query.error ?? run.error)!.message })}</Alert>}
        {query.isPending ? <Loader aria-label={t('common.loading')} /> : b && (
          <>
            <Paper withBorder radius="lg" p="md" className={`fb-preflight-verdict ${verdict}`}>
              <Group justify="space-between" wrap="wrap">
                <Title order={2} size="h3">{t(`preflight.verdict.${verdict}`)}</Title>
                <Group gap={6}>
                  {(['pass', 'warn', 'fail', 'skip'] as const).map((s) => (
                    <Badge key={s} size="lg" variant="light" color={COLOR[s]} tt="none">{t(`preflight.count.${s}`, { count: b.counts[s] })}</Badge>
                  ))}
                </Group>
              </Group>
            </Paper>
            <SimpleGrid cols={{ base: 1, lg: 3 }}>
              {GROUPS.map((g) => {
                const group = b.groups[g]
                return (
                  <Paper key={g} withBorder radius="lg" p="md">
                    <Group justify="space-between" mb={4} wrap="nowrap">
                      <Title order={2} size="h4">{t(`preflight.group.${g}`)}</Title>
                      {canRun && (
                        <Button size="xs" variant="default" loading={busy(g)} onClick={() => run.mutate(g)}>
                          {group ? t('preflight.runAgain') : t('preflight.run')}
                        </Button>
                      )}
                    </Group>
                    <Text size="xs" c="dimmed" mb="sm">
                      {group ? t('preflight.ranBy', { when: when(group.at), who: group.by ?? '?' }) : t('preflight.notRun')}
                    </Text>
                    <Stack gap={8}>
                      {group?.items.map((i) => (
                        <Group key={i.id} gap="sm" wrap="nowrap" align="flex-start">
                          <Badge variant="filled" color={COLOR[i.status]} w={64} tt="none" style={{ flexShrink: 0 }}>{t(`preflight.status.${i.status}`)}</Badge>
                          <Stack gap={0} style={{ minWidth: 0 }}>
                            <Text size="sm" fw={600} style={{ overflowWrap: 'anywhere' }}>{i.name}</Text>
                            {i.detail && <Text size="xs" c="dimmed">{i.detail}</Text>}
                          </Stack>
                        </Group>
                      ))}
                    </Stack>
                  </Paper>
                )
              })}
            </SimpleGrid>
          </>
        )}
      </Stack>
    </Layout>
  )
}
