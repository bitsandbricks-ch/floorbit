/** Fri 14:05: shifts span midnight, so the day is part of the time. */
export function when(ts: number): string {
  return new Date(ts * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })
}
