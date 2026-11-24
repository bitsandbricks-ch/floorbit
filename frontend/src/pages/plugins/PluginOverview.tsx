import { Badge, Button, Group, Stack, Table, Text } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { post } from '@/api/client'
import type { ActionResult, Agent, PluginInfo } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { Panel } from '@/components/ui'
import { ago } from '@/lib/time'
import { Badges, DataSchema } from './parts'
import { pluginState, type PluginTone } from './status'

const TONE: Record<PluginTone, string> = { up: 'up', warn: 'warn', down: 'down', off: 'gray' }

/** The top of a plugin's page (#995): whether it works in one line, what it is, and its test and actions. */
export function PluginOverview({ plugin, agents }: { plugin: PluginInfo; agents?: Agent[] }) {
  const { t } = useTranslation()
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const done = (ok: boolean, text: string) => setResult({ ok, text })
  const test = useMutation({
    mutationFn: () => post<{ ok: boolean; message: string }>(`/api/settings/plugins/${encodeURIComponent(plugin.id)}/test`),
    onSuccess: (r) => done(r.ok, r.message),
    onError: (e) => done(false, e.message),
  })
  const action = useMutation({
    mutationFn: (id: string) => post<ActionResult>(`/api/plugins/${encodeURIComponent(plugin.id)}/actions/${encodeURIComponent(id)}`),
    onSuccess: (r) => done(true, r.message),
    onError: (e) => done(false, e.message),
  })
  const busy = test.isPending || action.isPending
  const state = pluginState(plugin, agents)
  const buttons = plugin.enabled && (plugin.has_test || plugin.actions.length > 0)
  return (
    <Panel>
      <Stack gap="sm">
        <Group gap="sm" wrap="wrap" align="center">
          <Badge size="lg" variant="light" color={TONE[state.tone]} tt="none" data-testid="plugin-state">
            {t(`plugins.state.${state.key}.title`)}
          </Badge>
          <Text size="sm" role="status">{t(`plugins.state.${state.key}.text`, state.values)}</Text>
        </Group>
        <Group gap="sm" wrap="wrap"><Badges plugin={plugin} /></Group>
        {plugin.schema ? <DataSchema plugin={plugin} /> : null}
        {buttons && (
          <Group gap="xs" wrap="wrap">
            {plugin.has_test && <Button variant="default" disabled={busy} onClick={() => test.mutate()}>{t('plugins.test')}</Button>}
            {plugin.actions.map((a) => (
              <ConfirmButton key={a.id} variant="default" label={a.label} danger={a.danger} title={a.help} disabled={busy} onConfirm={() => action.mutate(a.id)} />
            ))}
          </Group>
        )}
        {(busy || result) && (
          <Text size="sm" role="status" className={result && !busy ? (result.ok ? 'fb-tone-ok' : 'fb-tone-err') : undefined}>
            {test.isPending ? t('plugins.testing') : action.isPending ? t('common.working') : result ? `${result.ok ? '✓' : '✕'} ${result.text}` : ''}
          </Text>
        )}
      </Stack>
    </Panel>
  )
}

/** How the plugin's agent part does on each local agent, from their last report. */
export function PerAgent({ plugin, agents }: { plugin: PluginInfo; agents: Agent[] }) {
  const { t } = useTranslation()
  if (!agents.length) return <Text size="sm" c="dimmed">{t('plugins.perAgent.none')}</Text>
  return (
    <Table verticalSpacing="sm" className="fb-table-stack" aria-label={t('plugins.perAgent.title')}>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>{t('plugins.perAgent.agent')}</Table.Th>
          <Table.Th>{t('plugins.perAgent.state')}</Table.Th>
          <Table.Th>{t('plugins.perAgent.lastError')}</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {agents.map((a) => {
          const h = a.report?.plugins?.[plugin.id]
          const last = h?.errors[h.errors.length - 1]
          const tone = !h?.running ? 'gray' : h.status === 'error' ? 'down' : h.status === 'warning' ? 'warn' : 'up'
          return (
            <Table.Tr key={a.id}>
              <Table.Td className="fb-stack-inline"><Text size="sm" fw={600}>{a.name}</Text></Table.Td>
              <Table.Td data-label={t('plugins.perAgent.state')}>
                <Badge variant="light" color={tone} tt="none">
                  {h?.running ? t(`agents.pluginStatus.${h.status}`) : t('agents.pluginNotRunning')}
                </Badge>
                {h?.message && <Text size="xs" c="dimmed" mt={2} style={{ overflowWrap: 'anywhere' }}>{h.message}</Text>}
              </Table.Td>
              <Table.Td data-label={t('plugins.perAgent.lastError')}>
                {last ? <Text size="xs" style={{ overflowWrap: 'anywhere' }}>{last.at ? `${ago(last.at)} · ` : ''}{last.error}</Text>
                  : <Text size="xs" c="dimmed">{t('plugins.perAgent.noError')}</Text>}
              </Table.Td>
            </Table.Tr>
          )
        })}
      </Table.Tbody>
    </Table>
  )
}
