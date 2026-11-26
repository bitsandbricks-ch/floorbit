import { Stack, Text, UnstyledButton, Collapse } from '@mantine/core'
import { IconChevronRight } from '@tabler/icons-react'
import { useMutation, useQueries, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, patch } from '@/api/client'
import { qk } from '@/api/keys'
import type { Agent, AgentPluginField, AgentSettingsPage, AgentTagSettingsPage, InheritedValue, PluginInfo } from '@/api/types'
import { Panel } from '@/components/ui'
import { useLeaveWarning } from '@/components/useLeaveWarning'
import { ErrorBanner } from '@bitsandbricks/ui'
import { Input, Row, Source } from '@/pages/agents/fields'
import { useAgentTags } from '@/pages/agents/data'
import { fieldId, shown, type Value } from '@/pages/agents/values'
import { SaveBar } from '@/pages/settings/editor'

/** Drafts by fold: ``tag:<id>`` or ``agent:<id>``. */
type Drafts = Record<string, Record<string, Value>>

const tagKey = (id: string) => [...qk.agents, 'tags', id, 'settings']
const agentKey = (id: string) => [...qk.agents, id, 'settings']

/** The plugin's settings that may differ per agent (#990), inherited like the inventory (#1591):
 *  one fold per tag the agents have (every agent with it gets the value), then one per agent for
 *  what differs on that machine. Saved together. */
export function PerAgentSettings({ plugin, agents }: { plugin: PluginInfo; agents: Agent[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const names = useAgentTags().names
  const tagIds = [...new Set(agents.flatMap((a) => a.tags ?? []))]
  const tagPages = useQueries({
    queries: tagIds.map((id) => ({ queryKey: tagKey(id), queryFn: () => get<AgentTagSettingsPage>(`/api/agents/tags/${encodeURIComponent(id)}/settings`) })),
  })
  const pages = useQueries({
    queries: agents.map((a) => ({ queryKey: agentKey(a.id), queryFn: () => get<AgentSettingsPage>(`/api/agents/${a.id}/settings`) })),
  })
  const [draft, setDraft] = useState<Drafts>({})
  const [saved, setSaved] = useState(false)
  const save = useMutation({
    mutationFn: async (changes: Drafts) => {
      // Tags first: the agents' pages then show what they inherit now.
      const order = Object.keys(changes).sort((a, b) => Number(b.startsWith('tag:')) - Number(a.startsWith('tag:')))
      for (const fold of order) {
        const [kind, id] = [fold.slice(0, fold.indexOf(':')), fold.slice(fold.indexOf(':') + 1)]
        const body = { plugins: { [plugin.id]: changes[fold] } }
        if (kind === 'tag') {
          qc.setQueryData(tagKey(id), await patch<AgentTagSettingsPage>(`/api/agents/tags/${encodeURIComponent(id)}/settings`, body))
        } else {
          qc.setQueryData(agentKey(id), await patch<AgentSettingsPage>(`/api/agents/${id}/settings`, body))
        }
        // One saved and the next refused: keep only what is still unsaved.
        setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => k !== fold)))
      }
      if (order.some((f) => f.startsWith('tag:'))) await qc.invalidateQueries({ queryKey: qk.agents })
    },
    onSuccess: () => setSaved(true),
  })
  const count = Object.values(draft).reduce((n, d) => n + Object.keys(d).length, 0)
  useLeaveWarning(count > 0)
  const mine = (p?: AgentSettingsPage) => p?.plugins.find((x) => x.id === plugin.id)
  const fields = pages.map((q) => mine(q.data)).find(Boolean)?.fields
  if (!fields?.length) return null
  const set = (fold: string, key: string, v: Value) => { setSaved(false); setDraft((d) => ({ ...d, [fold]: { ...d[fold], [key]: v } })) }
  const undo = (fold: string, key: string) => setDraft((d) => {
    const left = Object.fromEntries(Object.entries(d[fold] ?? {}).filter(([k]) => k !== key))
    const rest = Object.fromEntries(Object.entries(d).filter(([a]) => a !== fold))
    return Object.keys(left).length ? { ...rest, [fold]: left } : rest
  })
  const single = agents.length === 1 && tagIds.length === 0

  return (
    <form onSubmit={(e) => { e.preventDefault(); if (count) save.mutate(draft) }} autoComplete="off" noValidate>
      <Panel title={t('plugins.perAgent.settingsTitle')} desc={t('plugins.perAgent.settingsIntro')}>
        <Stack gap={0}>
          {tagIds.map((id, i) => {
            const page = tagPages[i].data
            const members = agents.filter((a) => a.tags?.includes(id)).map((a) => a.name)
            return (
              <Fold key={`tag:${id}`} foldId={`tag-${id}`} title={t('plugins.perAgent.tag', { name: names[id] ?? page?.tag.name ?? id })}
                sub={t('plugins.perAgent.tagAgents', { names: members.join(', ') })}
                fields={fields} values={page?.plugins.find((x) => x.id === plugin.id)?.values ?? {}} inherited={{}}
                error={tagPages[i].error} draft={draft[`tag:${id}`] ?? {}} single={false} own="tag"
                onSet={(k, v) => set(`tag:${id}`, k, v)} onUndo={(k) => undo(`tag:${id}`, k)} />
            )
          })}
          {agents.map((a, i) => (
            <Fold key={a.id} foldId={a.id} title={a.name} fields={fields} values={mine(pages[i].data)?.values ?? {}}
              inherited={mine(pages[i].data)?.inherited ?? {}} own="agent"
              error={pages[i].error} draft={draft[`agent:${a.id}`] ?? {}} single={single}
              onSet={(k, v) => set(`agent:${a.id}`, k, v)} onUndo={(k) => undo(`agent:${a.id}`, k)} />
          ))}
        </Stack>
      </Panel>
      {count > 0 && <div style={{ height: 96 }} />}
      <SaveBar count={count} bad={false} saving={save.isPending} error={save.error}
        saved={saved ? t('agents.cfg.saved') : null} onDiscard={() => setDraft({})} />
    </form>
  )
}

function Fold({ foldId, title, sub, fields, values, inherited, error, draft, single, own, onSet, onUndo }: {
  foldId: string; title: string; sub?: string; fields: AgentPluginField[]; values: Record<string, unknown>
  inherited: Record<string, InheritedValue>; error: Error | null; draft: Record<string, Value>; single: boolean
  own: 'tag' | 'agent'; onSet: (key: string, v: Value) => void; onUndo: (key: string) => void
}) {
  const { t } = useTranslation()
  const [shownNow, setShown] = useState(false)
  const opened = single || shownNow || Object.keys(draft).length > 0
  const setHere = fields.filter((f) => f.key in values)
  const fromTags = fields.filter((f) => !(f.key in values) && f.key in inherited)
  const summary = [
    ...setHere.map((f) => `${f.label}: ${shown(values[f.key]) || '–'}`),
    ...fromTags.map((f) => t('plugins.perAgent.fromTag', { label: f.label, value: shown(inherited[f.key].value) || '–', name: inherited[f.key].name })),
  ].join(' · ') || t('plugins.perAgent.same')
  return (
    <div className="fb-setting-advanced fb-agent-fold">
      <UnstyledButton className="fb-setting-advanced-toggle" aria-expanded={opened} onClick={() => setShown(!opened)} disabled={single}>
        {!single && <IconChevronRight size={14} className={opened ? 'is-open' : undefined} aria-hidden />}
        <Text size="sm" fw={600} component="span">{title}</Text>
        <Text size="xs" c="dimmed" component="span">{sub ? `${sub} · ${summary}` : summary}</Text>
      </UnstyledButton>
      <Collapse expanded={opened}>
        <ErrorBanner error={error} />
        <Stack gap={0} className="fb-setting-rows">
          {fields.map((f) => {
            const id = fieldId(`${foldId}-${f.key}`)
            const dirty = f.key in draft
            const value = (dirty ? draft[f.key] : values[f.key] ?? null) as Value
            const from = inherited[f.key]
            // What applies when this field is empty: the tag's value for an agent, else the plugin's.
            const fallback = from
              ? t('plugins.perAgent.tagValue', { value: shown(from.value) || '–', name: from.name })
              : t('agents.cfg.pluginDefault', { value: shown(f.default) || '–' })
            const differs = own === 'agent' && from && f.key in values && shown(values[f.key]) !== shown(from.value)
            return (
              <Row key={f.key} id={id} label={f.label} help={f.help ? `${f.help} ${fallback}` : fallback}
                dirty={dirty} onUndo={() => onUndo(f.key)} onReset={f.key in values ? () => onSet(f.key, null) : undefined}
                tags={f.key in values
                  ? <>
                    <Source source="floorbit" />
                    {differs && <Text size="xs" c="warn">{t('plugins.perAgent.differs', { name: from.name })}</Text>}
                  </>
                  : from ? <Text size="xs" c="dimmed">{t('plugins.perAgent.fromTagShort', { name: from.name })}</Text> : null}>
                <Input id={id} helpId={`${id}-help`} type={f.type} value={value} min={f.min} max={f.max} options={f.options}
                  placeholder={shown(from ? from.value : f.default) || f.placeholder || undefined} onChange={(v) => onSet(f.key, v)} />
              </Row>
            )
          })}
        </Stack>
      </Collapse>
    </div>
  )
}
