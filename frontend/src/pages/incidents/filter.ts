import type { Incident } from '@/api/types'

/** Does the incident match the board filter? Title, place, people, team and notes, ignoring case. */
export function matchesFilter(i: Incident, filter: string, teamNames: Record<string, string> = {}): boolean {
  const q = filter.trim().toLowerCase()
  if (!q) return true
  const fields = [i.title, i.seat, i.switch_name, i.switch_id, i.circuit_name, i.assignee, i.team, teamNames[i.team ?? ''],
    ...i.notes.map((n) => n.text)]
  return fields.some((f) => typeof f === 'string' && f.toLowerCase().includes(q))
}
