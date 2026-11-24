/** The four looks a state can have (#1016): working, broken, needs a look, and nothing to say. */
export type StateTone = 'up' | 'down' | 'warn' | 'off'

/** Every state word the pages use, and its one look: "offline" is red on every page. The labels are
 *  ``state.<word>`` (i18n/*\/state.json). */
export const STATE_TONE = {
  up: 'up', ok: 'up', online: 'up', live: 'up', active: 'up', connected: 'up',
  down: 'down', offline: 'down', failed: 'down', crit: 'down', tripped: 'down',
  warn: 'warn', degraded: 'warn', stale: 'warn', planning: 'warn',
  unknown: 'off', closed: 'off', idle: 'off', ended: 'off', disconnected: 'off',
} as const satisfies Record<string, StateTone>

export type StateWord = keyof typeof STATE_TONE

/** The tone of a state word; words this map doesn't know have nothing to say. */
export const toneOf = (state: string | null | undefined): StateTone =>
  (state && (STATE_TONE as Record<string, StateTone>)[state]) || 'off'

/** Mantine's colour for a tone (theme.ts registers up, down and warn). */
export const toneColor = (tone: StateTone) => (tone === 'off' ? 'gray' : tone)
