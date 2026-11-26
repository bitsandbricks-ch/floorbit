import { Badge, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { HostedState } from '@/api/types'
import { ago } from '@/lib/time'
import { StatusBadge } from '@bitsandbricks/ui'

/** This Floorbit itself: one instance or several, which one leads, and whether the database and Redis answer. */
export function HostedCard({ hosted }: { hosted?: HostedState }) {
  const { t, i18n } = useTranslation()
  if (!hosted) return null
  const ok = hosted.database.ok && (hosted.mode === 'single' || hosted.redis.ok)
  return (
    <Paper withBorder radius="lg" p="md" aria-labelledby="ha-hosted">
      <Group justify="space-between" mb="xs">
        <Title order={2} size="h4" id="ha-hosted">{t('agents.ha.hostedTitle')}</Title>
        <StatusBadge size="md" state={ok ? 'up' : 'down'} label={ok ? t('agents.ha.healthy') : t('agents.ha.unhealthy')} />
      </Group>
      <Stack gap={4}>
        <Text size="sm">
          {hosted.mode === 'single' ? t('agents.ha.single') : t('agents.ha.pods', { count: hosted.pods.length })}
        </Text>
        <Group gap={6} wrap="wrap">
          {hosted.pods.map((p) => (
            <Badge key={p.pod} variant={p.me ? 'filled' : 'light'} color={p.leader ? 'up' : 'gray'} tt="none">
              {p.pod}{p.leader ? ` · ${t('agents.ha.leader')}` : ''}{p.me ? ` · ${t('agents.ha.thisOne')}` : ''}
            </Badge>
          ))}
        </Group>
        <Text size="xs" c={hosted.database.ok ? 'dimmed' : 'down'}>
          {hosted.database.ok
            ? t('agents.ha.dbOk', { kind: hosted.database.kind })
            : t('agents.ha.dbDown', { kind: hosted.database.kind, when: hosted.database.since ? ago(hosted.database.since, i18n.language) : '?' })}
        </Text>
        <Text size="xs" c={hosted.redis.ok || hosted.mode === 'single' ? 'dimmed' : 'down'}>
          {hosted.redis.ok ? t('agents.ha.redisOk') : t(hosted.mode === 'single' ? 'agents.ha.redisOff' : 'agents.ha.redisDown')}
        </Text>
      </Stack>
    </Paper>
  )
}
