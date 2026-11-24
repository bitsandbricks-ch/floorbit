/** Muting from the Problems list and a problem's page (issues #10, #256, #882). */
export type MuteTarget = { id: string; name: string; kind: 'switch' | 'health' | 'wifi' }

/** What /api/alerts/mutes takes for each kind: a service and an access point by name, a switch by its id. */
export const muteBody = (v: MuteTarget) => v.kind === 'health' ? { service_id: v.id.replace(/^health:/, '') }
  : v.kind === 'wifi' ? { ap: v.name } : { switch_id: v.id }
const MUTE_KINDS = ['health', 'wifi'] as const
export const muteKind = (kind: string): MuteTarget['kind'] => (MUTE_KINDS as readonly string[]).includes(kind) ? kind as MuteTarget['kind'] : 'switch'
