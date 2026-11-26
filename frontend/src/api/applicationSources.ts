// Rule sources for the applications (docs/applications.md, "Rule sources"): files fetched on a schedule.
import { del, get, post, put } from './client'

export type RuleSource = {
  id: string
  name: string
  url: string
  every_hours: number
  on: boolean
  at: number | null
  ok: boolean | null
  error: string | null
  changed_at: number | null
  count: number
  /** Floorbit's own list: signed, always last, can be switched off but not removed or moved. */
  builtin?: boolean
  signed?: boolean
}
export type RuleSourcesAnswer = { sources: RuleSource[]; frozen: boolean }
export type RuleSourceBody = { name?: string; url?: string; every_hours?: number; on?: boolean; position?: number }
/** What every reader of the applications page sees of a source: no URL. */
export type SyncedSource = Pick<RuleSource, 'id' | 'name' | 'on' | 'ok' | 'changed_at' | 'count'>

export const SOURCES_URL = '/api/applications/sources'
export const ruleSourcesKey = ['applications', 'sources'] as const

export const fetchRuleSources = () => get<RuleSourcesAnswer>(SOURCES_URL)
export const addRuleSource = (body: RuleSourceBody) => post<RuleSource>(SOURCES_URL, body)
export const changeRuleSource = (id: string, body: RuleSourceBody) =>
  put<RuleSource>(`${SOURCES_URL}/${encodeURIComponent(id)}`, body)
export const removeRuleSource = (id: string) => del<{ ok: boolean }>(`${SOURCES_URL}/${encodeURIComponent(id)}`)
export const syncRuleSource = (id: string) => post<RuleSource>(`${SOURCES_URL}/${encodeURIComponent(id)}/sync`, {})
export const freezeRuleSources = (frozen: boolean) => put<RuleSourcesAnswer>('/api/applications/sources-frozen', { frozen })
