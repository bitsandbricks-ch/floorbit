import { Alert, Anchor, Button, Group, Modal, Stack, Text, TextInput } from '@mantine/core'
import { IconArrowUp, IconPlus } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import { qk } from '@/api/keys'
import { Layout } from '@/components/Layout'
import { ErrorBanner, LoadingState, PageHead, useFilters } from '@bitsandbricks/ui'
import AgentsView from './agents/AgentsView'
import { FILTERS } from './agents/listModel'
import { HostedCard } from './agents/Availability'
import { useAgents } from './agents/data'
import { KeyAlert, type Made } from './agents/KeyAlert'
import { behind } from './agents/model'

const DOCS = 'https://github.com/bitsandbricks-ch/floorbit/blob/master/docs/agent.md'

/** Local agents (issues #2, #1463): every agent in one list grouped by agent group, problems first,
 *  a side panel for one, and this Floorbit itself below; one agent's details, plugins, updates and
 *  settings are on its own page. */
export default function Agents() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { query, data: d, rows } = useAgents()
  const filters = useFilters(FILTERS)
  const [enrolling, setEnrolling] = useState(false)
  const [name, setName] = useState('')
  const [made, setMade] = useState<Made | null>(null)
  const make = useMutation({
    mutationFn: () => post<Made>('/api/agents', { name: name.trim() }),
    onSuccess: (m) => { setMade(m); setName(''); setEnrolling(false); void qc.invalidateQueries({ queryKey: qk.agents }) },
  })
  const old = rows.filter((r) => r.agent.outdated || behind(r.agent, d?.newest_version)).length

  return (
    <Layout title={t('agents.title')} back={{ href: '/settings', label: t('agents.settings') }}>
      <PageHead title={t('agents.title')} desc={t('agents.intro')}
        actions={d && (
          <Group gap="xs">
            {old > 0 && (
              <Button variant="default" leftSection={<IconArrowUp size={16} />} title={t('agentList.updateTitle')}
                onClick={() => filters.set('show', 'old')}>{t('agentList.update', { count: old })}</Button>
            )}
            {d.agents.length < d.max && <Button leftSection={<IconPlus size={16} />} onClick={() => setEnrolling(true)}>{t('agents.new')}</Button>}
          </Group>
        )} />
      <Stack gap="md">
        <ErrorBanner error={query.error} />
        {made && <KeyAlert made={made} onClose={() => setMade(null)} />}
        {query.isPending ? <LoadingState rows={3} /> : d && (
          <>
            <AgentsView expanded />
            <Text size="xs" c="dimmed">{t('agents.inUse')}</Text>
            <HostedCard hosted={d.hosted} />
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
