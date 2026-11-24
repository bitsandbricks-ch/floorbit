/** Muting from the Problems list and a problem's page (issues #10, #256, #882, #887). */
export type MuteTarget = { id: string; name: string; kind: 'switch' | 'health' | 'wifi' | 'problem' }

/** The prefix of a mute that is a problem's own (floorbit/problems.py PROBLEM_MUTE). */
const PROBLEM = 'problem:'

/** What /api/alerts/mutes takes for each kind: a service and an access point by name, a switch by
 *  its id, any other problem by its id on the list. */
export const muteBody = (v: MuteTarget) => v.kind === 'health' ? { service_id: v.id.replace(/^health:/, '') }
  : v.kind === 'wifi' ? { ap: v.name }
  : v.kind === 'problem' ? { problem_id: v.id.slice(PROBLEM.length) } : { switch_id: v.id }

const MUTE_KINDS = ['health', 'wifi'] as const
export const muteKind = (kind: string, muteId?: string | null): MuteTarget['kind'] =>
  muteId?.startsWith(PROBLEM) ? 'problem'
    : (MUTE_KINDS as readonly string[]).includes(kind) ? kind as MuteTarget['kind'] : 'switch'

/** What the mute dialog works on for a problem on the list: a problem by its title. */
export function muteTarget(p: { kind: string; mute_id?: string | null; switch_id?: string | null; name?: string | null; where: string; title: string }): MuteTarget {
  const kind = muteKind(p.kind, p.mute_id)
  return { id: p.mute_id ?? p.switch_id ?? '', name: kind === 'problem' ? p.title : p.name ?? p.where, kind }
}

/** Where a running mute's name links to. */
export const muteHref = (m: { switch_id: string; kind: string; name: string }, wifi: string) =>
  m.kind === 'health' ? '/services' : m.kind === 'wifi' ? wifi
    : m.kind === 'problem' ? `/problems/${encodeURIComponent(m.switch_id.slice(PROBLEM.length))}`
      : `/plan?switch=${encodeURIComponent(m.name)}`
