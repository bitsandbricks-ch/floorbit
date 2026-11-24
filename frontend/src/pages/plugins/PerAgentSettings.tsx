import { Stack, Text, UnstyledButton, Collapse } from '@mantine/core'
import { IconChevronRight } from '@tabler/icons-react'
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, patch } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentPluginField, AgentSettingsPage, PluginInfo } from '@/api/types'
import { ErrorBanner, Panel } from '@/components/ui'
import { useLeaveWarning } from '@/components/useLeaveWarning'
import { Input, Row, Source } from '@/pages/agents/fields'
import { fieldId, shown, type Value } from '@/pages/agents/values'
import { SaveBar } from '@/pages/settings/editor'

type Drafts = Record<string, Record<string, Value>>

/** The plugin's settings that may differ per agent (#990): their one home, one fold per agent, saved together. */
export function PerAgentSettings({ plugin, agents }: { plugin: PluginInfo; agents: Agent[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const pages = useQueries({
    queries: agents.map((a) => ({
      queryKey: [...qk.agents, a.id, 'settings'],
      queryFn: () => get<AgentSettingsPage>(`/api/agents/${a.id}/settings`),
    })),
  })
  const [draft, setDraft] = useState<Drafts>({})
  const [saved, setSaved] = useState(false)
  const save = useMutation({
    mutationFn: async (changes: Drafts) => {
      for (const [id, values] of Object.entries(changes)) {
        const page = await patch<AgentSettingsPage>(`/api/agents/${id}/settings`, { plugins: { [plugin.id]: values } })
        qc.setQueryData([...qk.agents, id, 'settings'], page)
        // One agent saved and the next refused: keep only what is still unsaved.
        setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => k !== id)))
      }
    },
    onSuccess: () => setSaved(true),
  })
  const count = Object.values(draft).reduce((n, d) => n + Object.keys(d).length, 0)
  useLeaveWarning(count > 0)
  const mine = (p?: AgentSettingsPage) => p?.plugins.find((x) => x.id === plugin.id)
  const fields = pages.map((q) => mine(q.data)).find(Boolean)?.fields
  if (!fields?.length) return null
  const set = (agent: string, key: string, v: Value) => { setSaved(false); setDraft((d) => ({ ...d, [agent]: { ...d[agent], [key]: v } })) }
  const undo = (agent: string, key: string) => setDraft((d) => {
    const left = Object.fromEntries(Object.entries(d[agent] ?? {}).filter(([k]) => k !== key))
    const rest = Object.fromEntries(Object.entries(d).filter(([a]) => a !== agent))
    return Object.keys(left).length ? { ...rest, [agent]: left } : rest
  })

  return (
    <form onSubmit={(e) => { e.preventDefault(); if (count) save.mutate(draft) }} autoComplete="off" noValidate>
      <Panel title={t('plugins.perAgent.settingsTitle')} desc={t('plugins.perAgent.settingsIntro')}> 
        <Stack gap={0}>
          {agents.map((a, i) => (
            <AgentFold key={a.id} agent={a} fields={fields} values={mine(pages[i].data)?.values ?? {}}
              error={pages[i].error} draft={draft[a.id] ?? {}} single={agents.length === 1}
              onSet={(k, v) => set(a.id, k, v)} onUndo={(k) => undo(a.id, k)} />
          ))}
        </Stack>
      </Panel>
      {count > 0 && <div style={{ height: 96 }} />}
      <SaveBar count={count} bad={false} saving={save.isPending} error={save.error}
        saved={saved ? t('agents.cfg.saved') : null} onDiscard={() => setDraft({})} />
    </form>
  )
}

function AgentFold({ agent, fields, values, error, draft, single, onSet, onUndo }: {
  agent: Agent; fields: AgentPluginField[]; values: Record<string, unknown>; error: Error | null
  draft: Record<string, Value>; single: boolean; onSet: (key: string, v: Value) => void; onUndo: (key: string) => void
}) {
  const { t } = useTranslation()
  const [shownNow, setShown] = useState(false)
  const opened = single || shownNow || Object.keys(draft).length > 0
  const set = fields.filter((f) => f.key in values)
  const summary = set.length ? set.map((f) => `${f.label}: ${shown(values[f.key]) || '–'}`).join(' · ') : t('plugins.perAgent.same')
  return (
    <div className="fb-setting-advanced fb-agent-fold">
      <UnstyledButton className="fb-setting-advanced-toggle" aria-expanded={opened} onClick={() => setShown(!opened)} disabled={single}>
        {!single && <IconChevronRight size={14} className={opened ? 'is-open' : undefined} aria-hidden />}
        <Text size="sm" fw={600} component="span">{agent.name}</Text>
        <Text size="xs" c="dimmed" component="span">{summary}</Text>
      </UnstyledButton>
      <Collapse expanded={opened}>
        <ErrorBanner error={error} />
        <Stack gap={0} className="fb-setting-rows">
          {fields.map((f) => {
            const id = fieldId(`${agent.id}-${f.key}`)
            const dirty = f.key in draft
            const value = (dirty ? draft[f.key] : values[f.key] ?? null) as Value
            const fallback = t('agents.cfg.pluginDefault', { value: shown(f.default) || '–' })
            return (
              <Row key={f.key} id={id} label={f.label} help={f.help ? `${f.help} ${fallback}` : fallback}
                dirty={dirty} onUndo={() => onUndo(f.key)} onReset={f.key in values ? () => onSet(f.key, null) : undefined}
                tags={<Source source={f.key in values ? 'floorbit' : 'default'} />}>
                <Input id={id} helpId={`${id}-help`} type={f.type} value={value} min={f.min} max={f.max} options={f.options}
                  placeholder={shown(f.default) || f.placeholder || undefined} onChange={(v) => onSet(f.key, v)} />
              </Row>
            )
          })}
        </Stack>
      </Collapse>
    </div>
  )
}
