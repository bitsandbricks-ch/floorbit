import { Anchor, Badge, Group, Progress, SimpleGrid, Stack, Table, Text, ThemeIcon, Title, Tooltip } from '@mantine/core'
import { IconServer2 } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { useAgentGroup, type AgentGroupDetail, type AgentGroupMember } from '@/api/agentGroups'
import { Layout } from '@/components/Layout'
import { Card, EmptyState, ErrorBanner, LoadingState, PanelField } from '@bitsandbricks/ui'
import { Capabilities } from './agents/Capabilities'
import { agentHref } from './agents/data'
import { STATE_COLOR } from './agents/listModel'

const ROLE_COLOR: Record<AgentGroupMember['role'], string> = { primary: 'up', standby: 'gray', active: 'gray', offline: 'down' }
// One colour per agent in the split bar, in the order the group lists them.
const SHARE_COLOR = ['blue', 'teal', 'grape', 'orange', 'cyan', 'lime']

/** One group of local agents (#1441): who is primary, which devices each one owns, the shared
 *  addresses. Reached from a group's strip on the Local agents list. */
export default function AgentGroup() {
  const { t } = useTranslation()
  const { gid = '' } = useParams()
  const query = useAgentGroup(gid)
  const back = { href: '/settings/agents', label: t('agents.title') }
  const g = query.data

  if (query.isPending) return <Layout title={t('agentGroup.kicker')} back={back}><LoadingState rows={3} /></Layout>
  if (!g) {
    return (
      <Layout title={t('agentGroup.kicker')} back={back}>
        <EmptyState title={t('agentGroup.gone')} description={t('agentGroup.goneHelp')} />
      </Layout>
    )
  }
  const name = g.label || t('agentGroup.allDevices')
  return (
    <Layout title={name} back={back}>
      <Stack gap="md">
        <ErrorBanner error={query.error} />
        <Group align="flex-start" gap="md" wrap="nowrap">
          <ThemeIcon size={48} radius="md" variant="default" aria-hidden="true"><IconServer2 size={24} /></ThemeIcon>
          <Stack gap={6} style={{ minWidth: 0 }}>
            <Text size="xs" c="dimmed" tt="uppercase" ff="monospace">{t('agentGroup.kicker')}</Text>
            <Group gap="sm" wrap="wrap" align="center">
              <Title order={2} style={{ overflowWrap: 'anywhere' }}>{name}</Title>
              <Badge variant="dot" color={STATE_COLOR[g.state]} tt="none">{t(`agents.ha.state.${g.state}`)}</Badge>
              {g.mode && <Badge variant="outline" color="gray" tt="none">{t(`agents.ha.mode.${g.mode}`)}</Badge>}
            </Group>
            <Group gap={6} wrap="wrap">
              <Badge variant="default" tt="none" fw={500}>{g.tags.length ? t('agentGroup.tags', { tags: g.label }) : t('agentGroup.noTags')}</Badge>
              <Badge variant="default" tt="none" fw={500}>{t('agentGroup.agents', { count: g.agents.length })}</Badge>
            </Group>
            <Text size="sm" c="dimmed" maw={760}>{t('agentGroup.intro')}</Text>
            {g.state !== 'ok' && <Text size="sm" c={g.state === 'single' ? 'dimmed' : STATE_COLOR[g.state]}>{t(`agents.ha.help.${g.state}`)}</Text>}
          </Stack>
        </Group>

        <Card heading={2} title={t('agentGroup.agentsTitle')}>
          <SimpleGrid cols={{ base: 1, md: Math.min(g.agents.length, 3) }} spacing="md">
            {g.agents.map((a) => <AgentCard key={a.id} agent={a} total={g.devices} />)}
          </SimpleGrid>
        </Card>

        <Split group={g} />

        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          <Card heading={2} title={t('agentGroup.sendTitle')}>
            <Text size="sm">{t('agentGroup.sendHelp')}</Text>
          </Card>
          <SharedAddresses group={g} />
        </SimpleGrid>
      </Stack>
    </Layout>
  )
}

function AgentCard({ agent: a, total }: { agent: AgentGroupMember; total: number }) {
  const { t, i18n } = useTranslation()
  const num = (n: number) => n.toLocaleString(i18n.language)
  return (
    <Stack gap="xs" aria-label={a.name} component="article">
      <Group gap="xs" wrap="wrap">
        <Anchor component={Link} to={agentHref(a.id)} fw={600} style={{ overflowWrap: 'anywhere' }}>{a.name}</Anchor>
        <Badge variant="light" color={ROLE_COLOR[a.role]} tt="none">{t(`agents.ha.role.${a.role}`)}</Badge>
      </Group>
      <Text size="xs" c="dimmed">{t(`agentGroup.roleHelp.${a.role}`)}</Text>
      <PanelField label={t('agentGroup.fact.holds')}>{a.holds.length ? a.holds.join(', ') : t('agentGroup.fact.none')}</PanelField>
      <PanelField label={t('agentGroup.fact.owns')}>{a.connected && total > 0 ? t('agentGroup.fact.ownsValue', { n: num(a.owns), total: num(total) }) : '–'}</PanelField>
      {a.pinned > 0 && <PanelField label={t('agentGroup.fact.pinned')}>{num(a.pinned)}</PanelField>}
      {a.connected && <PanelField label={t('agentCapabilities.title')}><Capabilities have={a.capabilities} /></PanelField>}
      {a.version && <PanelField label={t('agentGroup.fact.version')}>{a.version}</PanelField>}
    </Stack>
  )
}

/** The devices per agent as one bar, and what happens when the busiest one stops. */
function Split({ group: g }: { group: AgentGroupDetail }) {
  const { t, i18n } = useTranslation()
  const num = (n: number) => n.toLocaleString(i18n.language)
  const live = g.agents.filter((a) => a.connected)
  const old = live.filter((a) => !a.follows_split).map((a) => a.name)
  const pinned = g.agents.reduce((n, a) => n + a.pinned, 0)
  const why = g.split ? t('agentGroup.splitOn')
    : g.agents.length < 2 ? t('agentGroup.splitAlone')
      : live.length < 2 ? t('agentGroup.splitOffline')
        : old.length ? t('agentGroup.splitOld', { names: old.join(', ') }) : t('agentGroup.splitWaiting')
  const busiest = g.split ? [...live].sort((x, y) => y.owns - x.owns)[0] : undefined
  const shares = g.agents.map((a, i) => ({ a, color: SHARE_COLOR[i % SHARE_COLOR.length] })).filter(({ a }) => a.owns + a.pinned > 0)
  return (
    <Card heading={2} title={t('agentGroup.splitTitle')}>
      <Stack gap="sm">
        {g.devices > 0 && (
          <>
            <Progress.Root size={22} aria-hidden="true">
              {shares.map(({ a, color }) => (
                <Tooltip key={a.id} label={t('agentGroup.share', { name: a.name, n: num(a.owns + a.pinned) })}>
                  <Progress.Section value={(100 * (a.owns + a.pinned)) / g.devices} color={color}>
                    <Progress.Label>{num(a.owns + a.pinned)}</Progress.Label>
                  </Progress.Section>
                </Tooltip>
              ))}
            </Progress.Root>
            <Group gap="md" wrap="wrap">
              {shares.map(({ a, color }) => (
                <Group key={a.id} gap={6} wrap="nowrap">
                  <ThemeIcon size={10} radius="xl" color={color} aria-hidden="true"><span /></ThemeIcon>
                  <Text size="sm">{t('agentGroup.share', { name: a.name, n: num(a.owns + a.pinned) })}</Text>
                </Group>
              ))}
            </Group>
          </>
        )}
        <Text size="sm" c={g.split || g.agents.length < 2 ? undefined : 'warn'}>{why}</Text>
        {pinned > 0 && <Text size="sm" c="dimmed">{t('agentGroup.pinnedNote', { count: pinned })}</Text>}
        {busiest && busiest.owns > 0 && <Text size="sm" c="dimmed">{t('agentGroup.whenStops', { name: busiest.name, n: num(busiest.owns) })}</Text>}
      </Stack>
    </Card>
  )
}

function SharedAddresses({ group: g }: { group: AgentGroupDetail }) {
  const { t } = useTranslation()
  const holder = (vip: string) => g.agents.find((a) => a.holds.includes(vip))?.name
  return (
    <Card heading={2} title={t('agentGroup.vipsTitle')}>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t('agentGroup.vipsHelp')}</Text>
        {g.vips.length === 0 ? <Text size="sm">{t('agentGroup.vipsNone')}</Text> : (
          <Table aria-label={t('agentGroup.vipsTitle')}>
            <Table.Thead>
              <Table.Tr><Table.Th>{t('agentGroup.vip.address')}</Table.Th><Table.Th>{t('agentGroup.vip.on')}</Table.Th></Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {g.vips.map((v) => (
                <Table.Tr key={v}><Table.Td ff="monospace">{v}</Table.Td><Table.Td>{holder(v) ?? t('agentGroup.vip.nobody')}</Table.Td></Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Stack>
    </Card>
  )
}
