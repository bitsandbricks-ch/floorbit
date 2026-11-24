import type { Incident } from '@/api/types'

/** Does the incident match the board filter? Title, place, people, team and notes, ignoring case.
 * ``seat:D-2`` matches that seat only, so links from a seat don't also catch D-20 to D-24;
 * ``switch:sw-a-01`` likewise matches one switch by name or id (issue #336), and ``with:kim`` the incidents
 * kim is on, not those that only mention kim in a note (issue #350). */
export function matchesFilter(i: Incident, filter: string, teamNames: Record<string, string> = {}): boolean {
  const q = filter.trim().toLowerCase()
  if (!q) return true
  if (q.startsWith('seat:')) return (i.seat ?? '').toLowerCase() === q.slice(5).trim()
  if (q.startsWith('switch:')) {
    const want = q.slice(7).trim()
    return [i.switch_name, i.switch_id].some((f) => typeof f === 'string' && f.toLowerCase() === want)
  }
  // ``id:<id>``: one incident, for links from a problem's page (issue #882).
  if (q.startsWith('id:')) return i.id.toLowerCase() === q.slice(3).trim()
  if (q.startsWith('with:')) return (i.assignee ?? '').toLowerCase() === q.slice(5).trim()
  const fields = [i.title, i.seat, i.switch_name, i.switch_id, i.circuit_name, i.assignee, i.team, teamNames[i.team ?? ''],
    ...i.notes.map((n) => n.text)]
  return fields.some((f) => typeof f === 'string' && f.toLowerCase().includes(q))
}
