import type { PowerState } from '@/api/types'

/** A circuit's state as a Mantine colour, and the order the counts are listed in (worst first). */
export const TONE: Record<PowerState, string> = { ok: 'up', warn: 'warn', crit: 'down', tripped: 'down', unknown: 'gray' }
export const ORDER: PowerState[] = ['tripped', 'crit', 'warn', 'ok', 'unknown']
