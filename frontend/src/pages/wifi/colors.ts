/** The colour of a load: green, amber from 50 %, red from the busy line. */
export function loadColor(pct: number | null, busy: number): string {
  if (pct == null) return 'var(--color-muted)'
  if (pct >= busy) return 'var(--color-down)'
  return pct >= 50 ? 'var(--color-warn)' : 'var(--color-up)'
}

/** One colour per channel, the same on every visit. */
export function channelColor(channel: number | null): string {
  return channel == null ? 'var(--color-muted)' : `hsl(${(channel * 67) % 360} 70% 50%)`
}
