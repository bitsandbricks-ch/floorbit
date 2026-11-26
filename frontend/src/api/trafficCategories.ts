// Traffic categories (docs/applications.md, "Categories"): the built-in seven plus the tenant's own (#1622).
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get, put } from './client'

export type TrafficCategory = { id: string; name: string; name_de: string; colour: string; builtin: boolean }
export type OwnCategory = Omit<TrafficCategory, 'builtin'>
export type TrafficCategoriesAnswer = { categories: TrafficCategory[]; palette: string[]; max_own: number }

export const CATEGORIES_URL = '/api/traffic/categories'
export const trafficCategoriesKey = ['traffic', 'categories'] as const

export const fetchTrafficCategories = () => get<TrafficCategoriesAnswer>(CATEGORIES_URL)
export const saveTrafficCategories = (categories: OwnCategory[]) =>
  put<TrafficCategoriesAnswer>(CATEGORIES_URL, { categories })

/** Until the list is in: the built-in ones, so pages never wait on it to draw. */
export const BUILTIN_CATEGORIES: TrafficCategory[] = [
  { id: 'gaming', name: 'Gaming', name_de: 'Gaming', colour: '#16a34a', builtin: true },
  { id: 'streaming', name: 'Streaming', name_de: 'Streaming', colour: '#9333ea', builtin: true },
  { id: 'social', name: 'Social', name_de: 'Soziale Medien', colour: '#db2777', builtin: true },
  { id: 'downloads', name: 'Downloads', name_de: 'Downloads', colour: '#2563eb', builtin: true },
  { id: 'updates', name: 'Updates', name_de: 'Updates', colour: '#d97706', builtin: true },
  { id: 'web', name: 'Web', name_de: 'Web', colour: '#0891b2', builtin: true },
  { id: 'other', name: 'Other', name_de: 'Anderes', colour: '#94a3b8', builtin: true },
]
export const BUILTIN_IDS = BUILTIN_CATEGORIES.map((c) => c.id)

export type Categories = {
  list: TrafficCategory[]
  /** The category as this tenant knows it: an id it doesn't have is "other". */
  of: (id: string | null | undefined) => TrafficCategory
  label: (id: string | null | undefined) => string
}

export function categoriesFrom(list: TrafficCategory[], lang: string): Categories {
  const byId = new Map(list.map((c) => [c.id, c]))
  const other = byId.get('other') ?? BUILTIN_CATEGORIES[BUILTIN_CATEGORIES.length - 1]
  const of = (id: string | null | undefined) => (id && byId.get(id)) || other
  return { list, of, label: (id) => (lang.startsWith('de') ? of(id).name_de : of(id).name) }
}

export function useTrafficCategories(): Categories & { palette: string[]; maxOwn: number } {
  const { i18n } = useTranslation()
  const q = useQuery({ queryKey: trafficCategoriesKey, queryFn: fetchTrafficCategories, staleTime: 60_000 })
  return { ...categoriesFrom(q.data?.categories ?? BUILTIN_CATEGORIES, i18n.language ?? 'en'),
    palette: q.data?.palette ?? [], maxOwn: q.data?.max_own ?? 30 }
}

/** A mix of bytes per category in the list's order, with an id the tenant lacks folded into "other". */
export function mixParts(mix: Record<string, number | undefined> | undefined, cats: Categories) {
  const sums = new Map<string, number>()
  for (const [id, v] of Object.entries(mix ?? {})) {
    if (typeof v !== 'number' || v <= 0) continue
    const key = cats.of(id).id
    sums.set(key, (sums.get(key) ?? 0) + v)
  }
  return cats.list.filter((c) => sums.has(c.id)).map((c) => ({ ...c, label: cats.label(c.id), bytes: sums.get(c.id)! }))
}
