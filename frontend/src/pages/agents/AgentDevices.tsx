import { Alert, Anchor, Stack, Text } from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { useAgentDevices } from '@/components/telemetry/api'
import { DeviceStateTable, type DeviceFilter } from '@/components/telemetry/DeviceStateTable'
import { Panel } from '@/components/ui'
import { ErrorBanner, LoadingState } from '@bitsandbricks/ui'

/** The devices one agent collects: their state, what came in and why one sends nothing (issue #1013). */
export function AgentDevices({ agentId }: { agentId: string }) {
  const { t } = useTranslation()
  const q = useAgentDevices(agentId)
  const [params, setParams] = useSearchParams()
  const filter: DeviceFilter = params.get('show') === 'look' ? 'look' : 'all'
  const onFilter = (f: DeviceFilter) => {
    const next = new URLSearchParams(params)
    if (f === 'look') next.set('show', 'look')
    else next.delete('show')
    setParams(next, { replace: true })
  }
  if (q.isPending) return <LoadingState rows={3} />
  if (q.error) return <ErrorBanner error={q.error} />
  const d = q.data
  return (
    <Stack gap="md">
      {d.error && (
        <Alert color={d.error === 'offline' ? 'down' : 'warn'} title={t(`agents.devices.error.${d.error}`)}>
          <Text size="sm">{t(`agents.devices.errorHelp.${d.error}`)}</Text>
          {d.error === 'no_telemetry' && <Anchor component={Link} to="/settings/plugins" size="sm">{t('agents.devices.turnOn')}</Anchor>}
          {d.detail && <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>{d.detail}</Text>}
        </Alert>
      )}
      {d.primary === false && <Alert color="gray" title={t('agents.devices.standby')}><Text size="sm">{t('agents.devices.standbyHelp')}</Text></Alert>}
      <Panel padding={0}>
        {d.devices.length
          ? <DeviceStateTable rows={d.devices} filter={filter} onFilter={onFilter} actions={d.connected && !d.error} />
          : <Text size="sm" c="dimmed" p="md">{t('agents.devices.none')}</Text>}
      </Panel>
    </Stack>
  )
}
