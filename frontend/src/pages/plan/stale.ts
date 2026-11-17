/** The plan asks every 30 s; three missed answers in a row means what's on screen is old. */
export const STALE_AFTER_MS = 90_000

/** How long the plan has gone without a fresh answer (ms), or 0 while it is fresh. */
export function staleFor(updatedAt: number, now: number, failing: boolean): number {
  if (!updatedAt) return 0
  const age = now - updatedAt
  return failing || age >= STALE_AFTER_MS ? Math.max(age, 0) : 0
}
