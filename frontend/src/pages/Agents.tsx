import { Alert, Anchor, Button, Group, Modal, Stack, Tabs, Text, TextInput } from '@mantine/core'
import { IconPlus } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { Layout } from '@/components/Layout'
import { PageHead } from '@bitsandbricks/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'
import AgentsView from './agents/AgentsView'
import { GroupsCard, HostedCard } from './agents/Availability'
import { useAgents } from './agents/data'
import { KeyAlert, type Made } from './agents/KeyAlert'

const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/agent.md'
const TABS = ['agents', 'failover', 'server'] as const
type Tab = (typeof TABS)[number]

/** Local agents (issue #2): how every agent does at a glance, failover per hall and this Floorbit
 *  itself, each on a tab; one agent's details, plugins, updates and settings are on its own page. */
export default function Agents() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { query, data: d, rows } = useAgents()
  const [params, setParams] = useSearchParams()
  const tab: Tab = (TABS as readonly string[]).includes(params.get('tab') ?? '') ? params.get('tab') as Tab : 'agents'
  const setTab = (v: string | null) => setParams(v && v !== 'agents' ? { tab: v } : {}, { replace: true })
  const [enrolling, setEnrolling] = useState(false)
  const [name, setName] = useState('')
  const [made, setMade] = useState<Made | null>(null)
  const make = useMutation({
    mutationFn: () => post<Made>('/api/agents', { name: name.trim() }),
    onSuccess: (m) => { setMade(m); setName(''); setEnrolling(false); void qc.invalidateQueries({ queryKey: qk.agents }) },
  })
  const groupsLook = (d?.groups ?? []).filter((g) => !['ok', 'single'].includes(g.state)).length
  const hostedOk = !d?.hosted || (d.hosted.database.ok && (d.hosted.mode === 'single' || d.hosted.redis.ok))

  return (
    <Layout title={t('agents.title')} back={{ href: '/settings', label: t('agents.settings') }}>
      <PageHead title={t('agents.title')} desc={t('agents.intro')}
        actions={d && d.agents.length < d.max && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setEnrolling(true)}>{t('agents.new')}</Button>
        )} />
      <Stack gap="md">
        <ErrorBanner error={query.error} />
        {made && <KeyAlert made={made} onClose={() => setMade(null)} />}
        {query.isPending ? <LoadingState rows={3} /> : d && (
          <>
            <Tabs value={tab} onChange={setTab} keepMounted={false}>
              <Tabs.List>
                <Tabs.Tab value="agents">{t('agents.tab.agents', { count: rows.length })}</Tabs.Tab>
                <Tabs.Tab value="failover" c={groupsLook ? 'down' : undefined}>
                  {t('agents.tab.failover')}{groupsLook ? ` · ${groupsLook}` : ''}
                </Tabs.Tab>
                <Tabs.Tab value="server" c={hostedOk ? undefined : 'down'}>{t('agents.tab.server')}</Tabs.Tab>
              </Tabs.List>
              <Tabs.Panel value="agents" pt="md">
                <AgentsView expanded />
                <Text size="xs" c="dimmed" mt="xs">{t('agents.inUse')}</Text>
              </Tabs.Panel>
              <Tabs.Panel value="failover" pt="md">
                {d.groups?.length ? <GroupsCard groups={d.groups} /> : <Text size="sm" c="dimmed">{t('agents.ha.noGroups')}</Text>}
              </Tabs.Panel>
              <Tabs.Panel value="server" pt="md">
                <HostedCard hosted={d.hosted} />
              </Tabs.Panel>
            </Tabs>
            <Text size="sm" c="dimmed"><Anchor href={DOCS} underline="always">{t('agents.docs')}</Anchor></Text>
          </>
        )}
      </Stack>
      <Modal opened={enrolling} onClose={() => setEnrolling(false)} title={t('agents.new')}>
        <Stack gap="sm">
          <TextInput label={t('agents.name')} description={t('agents.nameHelp')} value={name} maxLength={60} data-autofocus
            onChange={(e) => setName(e.currentTarget.value)} />
          {make.error && <Alert color="down" role="alert">{make.error.message}</Alert>}
          <Group justify="flex-end">
            <Button loading={make.isPending} disabled={!name.trim()} onClick={() => make.mutate()}>{t('agents.make')}</Button>
          </Group>
        </Stack>
      </Modal>
    </Layout>
  )
}
