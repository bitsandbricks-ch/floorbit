import { Badge, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import type { AgentGroup, HostedState } from '@/api/types'
import { ago } from '@/lib/time'
import { StatusBadge } from '@bitsandbricks/ui'

const STATE_COLOR: Record<AgentGroup['state'], string> = {
  ok: 'up', single: 'gray', degraded: 'warn', no_primary: 'down', no_vrrp: 'warn', split: 'down', down: 'down',
}
const ROLE_COLOR: Record<AgentGroup['agents'][number]['role'], string> = {
  primary: 'up', standby: 'gray', active: 'gray', offline: 'down',
}

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

/** Agents per hall with failover over VRRP (docs/agent.md): who is primary, active/active or
 *  active/passive, which addresses each holds, and what to fix. */
export function GroupsCard({ groups }: { groups?: AgentGroup[] }) {
  const { t } = useTranslation()
  if (!groups?.length) return null
  return (
    <Paper withBorder radius="lg" p="md" aria-labelledby="ha-groups">
      <Title order={2} size="h4" mb="xs" id="ha-groups">{t('agents.ha.groupsTitle')}</Title>
      <Stack gap="sm">
        {groups.map((g) => (
          <Stack key={g.id} gap={4} aria-label={g.label || t('agents.allHalls')}>
            <Group gap={6} wrap="wrap">
              <Text fw={600}>{g.label || t('agents.allHalls')}</Text>
              <Badge variant="light" color={STATE_COLOR[g.state]} tt="none">{t(`agents.ha.state.${g.state}`)}</Badge>
              {g.mode && <Badge variant="outline" color="gray" tt="none">{t(`agents.ha.mode.${g.mode}`)}</Badge>}
            </Group>
            <Group gap={6} wrap="wrap">
              {g.agents.map((a) => (
                <Badge key={a.id} variant="light" color={ROLE_COLOR[a.role]} tt="none">
                  {a.name} · {t(`agents.ha.role.${a.role}`)}{a.holds.length ? ` · ${a.holds.join(', ')}` : ''}
                </Badge>
              ))}
            </Group>
            <Text size="xs" c={g.state === 'ok' || g.state === 'single' ? 'dimmed' : STATE_COLOR[g.state]}>
              {t(`agents.ha.help.${g.state}`)}
            </Text>
          </Stack>
        ))}
        <Text size="xs" c="dimmed">{t('agents.ha.groupsHelp')}</Text>
      </Stack>
    </Paper>
  )
}
