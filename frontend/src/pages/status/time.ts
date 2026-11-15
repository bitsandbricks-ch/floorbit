/** "2026-11-15T22:00" from a datetime-local field, in the browser's time zone, as Unix seconds. */
export function fromLocal(value: string): number | null {
  const t = new Date(value).getTime()
  return Number.isNaN(t) ? null : t / 1000
}
