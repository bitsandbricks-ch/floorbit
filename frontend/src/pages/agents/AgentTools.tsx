import { Badge, Button, Group, MultiSelect, Stack, Text, TextInput } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { patch, post } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentUpdates } from '@/api/types'
import { ConfirmButton } from '@/components/ConfirmButton'
import { ago } from '@/lib/time'

/** Rename, a new key (the old one works until the agent uses the new one), and plugins left off. */
export function AgentRename({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [renaming, setRenaming] = useState<string | null>(null)
  const rename = useMutation({
    mutationFn: (name: string) => patch(`/api/agents/${agent.id}`, { name }),
    onSuccess: () => { setRenaming(null); void qc.invalidateQueries({ queryKey: qk.agents }) },
  })
  return (
    <Stack gap={4}>
      {renaming === null ? (
        <Group gap={6}>
          <Button size="compact-sm" variant="default" onClick={() => setRenaming(agent.name)}>{t('agents.rename')}</Button>
        </Group>
      ) : (
        <Group gap={6} align="flex-end">
          <TextInput size="xs" label={t('agents.newName')} value={renaming} maxLength={60}
            onChange={(e) => setRenaming(e.currentTarget.value)} />
          <Button size="compact-sm" disabled={!renaming.trim()} loading={rename.isPending}
            onClick={() => rename.mutate(renaming.trim())}>{t('agents.save')}</Button>
          <Button size="compact-sm" variant="subtle" onClick={() => setRenaming(null)}>{t('agents.cancel')}</Button>
        </Group>
      )}
      {rename.error && <Text size="xs" c="down" role="alert">{rename.error.message}</Text>}
    </Stack>
  )
}

/** A new key to copy into the agent's env by hand: for an agent that is away (else "Roll key"). */
export function NewKeyButton({ agent, onKey }: { agent: Agent; onKey: (made: { name: string; key: string }) => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const rotate = useMutation({
    mutationFn: () => post<{ name: string; key: string }>(`/api/agents/${agent.id}/rotate`),
    onSuccess: (m) => { onKey(m); void qc.invalidateQueries({ queryKey: qk.agents }) },
  })
  return (
    <>
      <ConfirmButton size="compact-sm" variant="default" danger label={t('agents.rotate')}
        question={t('agents.rotateQuestion', { name: agent.name })} loading={rotate.isPending} onConfirm={() => rotate.mutate()} />
      {rotate.error && <Text size="xs" c="down" role="alert">{rotate.error.message}</Text>}
    </>
  )
}

/** Which of the plugins that are on here this agent leaves to another one. */
export function PluginsOff({ agent }: { agent: Agent }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const set = useMutation({
    mutationFn: (ids: string[]) => patch(`/api/agents/${agent.id}`, { plugins_off: ids }),
    onSettled: () => void qc.invalidateQueries({ queryKey: qk.agents }),
  })
  const known = new Set([
    ...Object.keys(agent.report?.plugins ?? {}),
    ...Object.keys(agent.report?.updates?.plugins ?? {}),
    ...(agent.plugins_off ?? []),
  ])
  if (!known.size) return null
  return (
    <MultiSelect size="xs" mt={6} maw={420} label={t('agents.pluginsOff')} description={t('agents.pluginsOffHelp')}
      placeholder={agent.plugins_off?.length ? undefined : t('agents.pluginsOffNone')}
      data={[...known].sort()} value={agent.plugins_off ?? []} clearable onChange={(ids) => set.mutate(ids)} />
  )
}

const EVENT_COLOR: Record<AgentUpdates['events'][number]['event'], string> = {
  installed: 'up', kept: 'up', 'rolled back': 'down', refused: 'down', dropped: 'warn', waiting: 'gray',
}

/** The version each plugin runs, what waits and why, and the last rollouts. */
export function Updates({ updates }: { updates?: AgentUpdates }) {
  const { t, i18n } = useTranslation()
  if (!updates) return null
  const waiting = Object.entries(updates.plugins).filter(([, p]) => p.pending)
  const bundled = Object.entries(updates.plugins).filter(([, p]) => p.source === 'bundle')
  return (
    <Stack gap={2} mt={4} aria-label={t('agents.updates.title')}>
      <Text size="xs" c="dimmed">
        {t(`agents.updates.policy.${updates.policy}`)}
        {' · '}{t('agents.updates.image', { v: updates.image })}
        {!updates.signed && <>{' · '}<Text span size="xs" c="warn">{t('agents.updates.noKey')}</Text></>}
      </Text>
      {bundled.map(([id, p]) => (
        <Text key={id} size="xs" c="dimmed">
          {t('agents.updates.runs', { plugin: id, v: p.version })}{p.probation ? ` · ${t('agents.updates.probation')}` : ''}
        </Text>
      ))}
      {waiting.map(([id, p]) => (
        <Text key={id} size="xs" c="warn">{t('agents.updates.waiting', { plugin: id, v: p.pending?.version, why: p.pending?.why })}</Text>
      ))}
      {updates.events.slice(-5).reverse().map((e) => (
        <Group key={`${e.at}-${e.plugin}-${e.event}`} gap={6} wrap="nowrap" align="flex-start">
          <Badge size="xs" variant="light" color={EVENT_COLOR[e.event] ?? 'gray'} tt="none" style={{ flexShrink: 0 }}>
            {t(`agents.updates.event.${e.event.replace(' ', '_')}`)}
          </Badge>
          <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
            {e.plugin} {e.version} · {ago(e.at, i18n.language)}{e.detail ? ` · ${e.detail}` : ''}
          </Text>
        </Group>
      ))}
    </Stack>
  )
}
