import { Anchor, Badge, Group, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { AgentGroup } from '@/api/types'
import { groupHref } from './data'
import { failoverText } from './failoverText'
import { STATE_COLOR } from './listModel'


export function FailoverCard({ agentId, groups }: { agentId: string; groups?: AgentGroup[] }) {
  const { t } = useTranslation()
  const g = groups?.find((x) => x.agents.some((a) => a.id === agentId))
  if (!g) return <Text size="sm" c="dimmed">{t('agentDetail.failover.unknown')}</Text>
  const href = groupHref(g.id)
  return (
    <Stack gap="xs">
      <Group gap="xs" wrap="wrap">
        <Text size="sm" fw={500}>{g.label || t('agents.allDevices')}</Text>
        <Badge size="sm" variant="light" color={STATE_COLOR[g.state]} tt="none">{t(`agents.ha.state.${g.state}`)}</Badge>
      </Group>
      <Text size="sm">{failoverText(agentId, g, t)}</Text>
      {href && <Anchor component={Link} to={href} size="sm">{t('agentDetail.failover.group')}</Anchor>}
    </Stack>
  )
}
