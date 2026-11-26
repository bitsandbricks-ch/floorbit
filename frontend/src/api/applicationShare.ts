// Sharing applications (issue #1612): as a file for floorbit-plugins' games/ folder, which a
// pull request adds to Floorbit's own list, or as a rules file another Floorbit imports.
import type { Application } from './applications'
import { post } from './client'
import { BUILTIN_IDS } from './trafficCategories'

/** What leaves the event: what an application matches, nothing it saw. */
export type SharedEntry = Pick<Application, 'id' | 'name' | 'kind' | 'category' | 'part_of' | 'sites' | 'ports' | 'cidr' | 'depots'>

export const GAMES_NEW_FILE = 'https://github.com/bitsandbricks-ch/floorbit-plugins/new/main/games'
// GitHub refuses longer addresses; a bigger entry is downloaded and added by hand.
export const MAX_URL = 7000

/** ``everywhere``: for Floorbit's own list, which keeps to the built-in categories (#1622), so an
 *  entry means the same on every Floorbit; a tenant's own category goes as "other". */
export function sharedEntry(a: Application, everywhere = false): SharedEntry {
  const category = everywhere && !BUILTIN_IDS.includes(a.category) ? 'other' : a.category
  return { id: a.id, name: a.name, kind: a.kind, category, part_of: a.part_of,
    sites: a.sites, ports: a.ports, cidr: a.cidr, depots: a.depots }
}

// JSON strings are YAML strings, so every value is quoted the same safe way.
const q = (v: string) => JSON.stringify(v)
const list = (vs: string[]) => `[${vs.map(q).join(', ')}]`

/** The entry as floorbit-plugins' games/<id>.yaml, with where its facts come from. */
export function gamesFile(e: SharedEntry, source: string): string {
  const lines = [`id: ${q(e.id)}`, `name: ${q(e.name)}`, `kind: ${q(e.kind)}`, `category: ${q(e.category)}`]
  if (e.kind === 'game' && e.part_of) lines.push(`part_of: ${q(e.part_of)}`)
  for (const k of ['sites', 'ports', 'cidr', 'depots'] as const) if (e[k].length) lines.push(`${k}: ${list(e[k])}`)
  lines.push(`source: ${q(source.replace(/\s+/g, ' ').trim())}`)
  return lines.join('\n') + '\n'
}

export function shareUrl(e: SharedEntry, source: string): string {
  const params = new URLSearchParams({ filename: `${e.id}.yaml`, value: gamesFile(e, source) })
  return `${GAMES_NEW_FILE}?${params.toString()}`
}

/** A rules file: what a rule source fetches and the Import button takes. */
export function rulesFile(entries: SharedEntry[]): string {
  return JSON.stringify({ version: 1, applications: entries.map((e) => ({ ...e, part_of: e.kind === 'game' ? e.part_of : null })) }, null, 2) + '\n'
}

export function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export const importApplications = async (file: File) =>
  post<{ added: number; changed: number }>('/api/applications/import', { file: await file.text() })
