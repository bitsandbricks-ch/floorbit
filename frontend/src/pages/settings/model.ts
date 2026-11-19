import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { get, post, put } from '@/api/client'
import { qk } from '@/api/keys'

type FieldType = 'url' | 'text' | 'secret' | 'list' | 'bool' | 'int' | 'choice' | 'color' | 'image'
export type Field = {
  key: string; section: string; label: string; type: FieldType; env: string | null
  help?: string; placeholder?: string; unit?: string; min?: number; max?: number; theme?: string
  options?: { value: string; label: string }[]
}
export type Value = { source: 'saved' | 'env' | 'hosted' | 'default'; value?: unknown; is_set?: boolean; unreadable?: boolean; env?: string; env_set?: boolean }
export type SettingsAnswer = {
  sections: { id: string; title: string; description: string }[]
  fields: Field[]
  values: Record<string, Value>
  status: { netbox_enabled: boolean; librenms_enabled: boolean; redis: { connected: boolean; host?: string; port?: number } | null }
}
export type TestResult = { ok: boolean; message: string }
export type Changes = Record<string, unknown>   // key -> new value, or null for "reset"

export const TESTABLE = new Set(['netbox', 'librenms'])
export const HEX = /^#[0-9a-f]{6}$/i
// i18next splits keys on dots; the setting keys have them.
export const k = (key: string) => key.replace(/\./g, '_')
// The settings that integrations and the built-in plugins add have their texts in integrationSettings.json.
export const keys = (path: string) => [`settings.${path}`, `integrationSettings.${path}`]

/** Is a typed value one the server takes? Bad ones stay unsaved and mark the field. */
export function invalid(f: Field, v: unknown): boolean {
  if (f.type === 'url') return typeof v === 'string' && v !== '' && !/^https?:\/\//i.test(v)
  if (f.type === 'color') return typeof v === 'string' && v !== '' && !HEX.test(v)
  if (f.type === 'int') return typeof v !== 'number' || !Number.isInteger(v) || (f.min != null && v < f.min) || (f.max != null && v > f.max)
  return false
}

/** Runs a connection test with the form's unsaved values for that service. */
export function useTest(changes: Changes) {
  const [results, setResults] = useState<Record<string, TestResult | 'running'>>({})
  const run = async (service: string) => {
    setResults((r) => ({ ...r, [service]: 'running' }))
    const body: Changes = {}
    for (const [key, v] of Object.entries(changes)) if (key.startsWith(service + '.') && v !== null) body[key] = v
    try {
      const r = await post<TestResult>(`/api/settings/test/${service}`, body)
      setResults((rs) => ({ ...rs, [service]: r }))
    } catch (e) {
      setResults((rs) => ({ ...rs, [service]: { ok: false, message: (e as Error).message } }))
    }
  }
  return { results, run }
}

/** The settings schema from GET /api/settings and the unsaved changes, shared by the Settings
 *  pages and each plugin's page. Saves only what changed; ``null`` resets a field to its
 *  environment variable or built-in default. */
/** ``enabled`` false: don't ask the server (an account that may open Settings' people pages but not its fields). */
export function useSettingsEditor({ enabled = true }: { enabled?: boolean } = {}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const query = useQuery({ queryKey: qk.settings, queryFn: () => get<SettingsAnswer>('/api/settings'), enabled })
  const [changes, setChanges] = useState<Changes>({})
  const [saved, setSaved] = useState<string | null>(null)
  const test = useTest(changes)
  const save = useMutation({
    mutationFn: (body: Changes) => put<SettingsAnswer>('/api/settings', body),
    onSuccess: (answer, body) => {
      qc.setQueryData(qk.settings, answer)
      setChanges({})
      const theme = Object.keys(body).some((key) => key.startsWith('theme.'))
      setSaved(t(theme ? 'settings.savedTheme' : 'settings.saved'))
      // The server puts the theme on <html> with the page, so show a new one by loading it again.
      if (theme) setTimeout(() => window.location.reload(), 600)
    },
  })
  const d = query.data
  const count = Object.keys(changes).length
  const bad = !!d && Object.entries(changes).some(([key, v]) => {
    const f = d.fields.find((x) => x.key === key)
    return !!f && v !== null && invalid(f, v)
  })

  useEffect(() => {
    if (!count) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [count])

  const setField = (f: Field, v: unknown) => {
    setSaved(null)
    const original = f.type === 'secret' ? '' : d?.values[f.key]?.value
    setChanges((c) => {
      const next = { ...c }
      if (JSON.stringify(v) === JSON.stringify(original)) delete next[f.key]
      else next[f.key] = v
      return next
    })
  }
  const drop = (key: string) => setChanges((c) => { const next = { ...c }; delete next[key]; return next })
  const reset = (key: string) => setChanges((c) => ({ ...c, [key]: null }))
  const current = (key: string) => (key in changes && changes[key] !== null ? changes[key] : d?.values[key]?.value)
  const discard = () => { setChanges({}); setSaved(null) }
  return { query, d, changes, count, bad, save, saved, test, setField, drop, reset, current, discard }
}

export type SettingsEditor = ReturnType<typeof useSettingsEditor>

export function sectionTitle(t: TFunction, s: { id: string; title: string }) {
  return t(keys(`sections.${s.id}.title`), { defaultValue: s.title })
}

