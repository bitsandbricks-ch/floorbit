import type { Problem } from '@/api/types'

/** A row on the Problems page: a problem, or a group of the same seat problem (issue #1415). */
export interface Row extends Problem {
  /** The seats' own problems, when this row stands for several. */
  members?: Problem[]
  /** Links that are down because a box at their end is: shown under the box, not as rows of their own. */
  links?: Problem[]
}

/** This many seats with the same problem become one row. */
export const GROUP_FROM = 3
/** Seat problems that read the same on every seat. A log line or an incident says something of its own. */
export const GROUPED_KINDS: readonly string[] = ['checkin', 'flapping', 'errors', 'duplex']

const lower = (s?: string | null) => (s ?? '').toLowerCase()

/**
 * Folds the list the way people read it: a down link hangs under the down box at either end, and
 * the same seat problem on many seats is one row that opens to the seats. ``keep`` names kinds the
 * person filtered to on purpose: those stay one row each.
 */
export function fold(rows: Problem[], keep: (kind: string) => boolean = () => false): Row[] {
  const boxes = new Map<string, Row>()
  const out: Row[] = []
  for (const p of rows) {
    const row: Row = { ...p }
    if (p.level === 'down' && p.kind !== 'link') {
      for (const name of [p.name, p.device]) if (name) boxes.set(lower(name), row)
    }
    out.push(row)
  }
  const linked = new Set<string>()
  for (const row of out) {
    if (row.kind !== 'link' || !row.ends) continue
    const box = row.ends.map((e) => boxes.get(lower(e))).find(Boolean)
    if (!box) continue
    box.links = [...(box.links ?? []), row]
    linked.add(row.id)
  }
  const kept = out.filter((r) => !linked.has(r.id))
  const bySeatKind = new Map<string, Row[]>()
  for (const r of kept) {
    if (!r.seat || r.muted || r.raised || !GROUPED_KINDS.includes(r.kind) || keep(r.kind)) continue
    const key = `${r.kind}:${r.level}`
    bySeatKind.set(key, [...(bySeatKind.get(key) ?? []), r])
  }
  const grouped = new Map<string, Row>()
  for (const [key, members] of bySeatKind) {
    if (members.length < GROUP_FROM) continue
    const first = members[0]!
    const since = members.map((m) => m.since).filter((s): s is number => s != null)
    grouped.set(key, {
      ...first, id: `group:${key}`, members, seat: null, link: '', incident: undefined, mute_id: undefined,
      clear_id: undefined, switch_id: undefined, cause: undefined, seats: undefined, behind: undefined,
      since: since.length ? Math.min(...since) : null,
      priority: Math.min(...members.map((m) => m.priority ?? 3)) as 1 | 2 | 3,
    })
  }
  const done = new Set<string>()
  const result: Row[] = []
  for (const r of kept) {
    const key = `${r.kind}:${r.level}`
    const group = grouped.get(key)
    if (group && group.members?.includes(r)) {
      if (!done.has(key)) { result.push(group); done.add(key) }
      continue
    }
    result.push(r)
  }
  return result
}
