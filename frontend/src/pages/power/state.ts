import type { PowerState } from '@/api/types'
import { STATE_TONE, toneColor } from '@bitsandbricks/ui'

/** A circuit's state as a Mantine colour (the shared state looks, #1016), and the order the counts
 *  are listed in (worst first). */
export const TONE: Record<PowerState, string> = {
  ok: toneColor(STATE_TONE.ok), warn: toneColor(STATE_TONE.warn), crit: toneColor(STATE_TONE.crit),
  tripped: toneColor(STATE_TONE.tripped), unknown: toneColor(STATE_TONE.unknown),
}
export const ORDER: PowerState[] = ['tripped', 'crit', 'warn', 'ok', 'unknown']

export const circuitPath = (id: string) => `/power/circuits/${encodeURIComponent(id)}`
export const boardPath = (id: string) => `/power/boards/${encodeURIComponent(id)}`
