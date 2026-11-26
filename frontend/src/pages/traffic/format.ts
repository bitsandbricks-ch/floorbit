import type { FlowCategory, FlowMix, FlowService } from '@/api/types'

/** Bytes as people say them: 80 GB, 1.2 TB. */
export function bytes(value: number | null | undefined): string {
  const v = value ?? 0
  const units = ['B', 'kB', 'MB', 'GB', 'TB', 'PB']
  let i = 0
  let n = v
  while (n >= 1000 && i < units.length - 1) { n /= 1000; i++ }
  return `${n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)} ${units[i]}`
}

export function total(mix: FlowMix | undefined): number {
  return Object.values(mix ?? {}).reduce<number>((sum, v) => sum + (typeof v === 'number' ? v : 0), 0)
}

/** The biggest category of a mix, for "mostly gaming". */
export function mostly(mix: FlowMix | undefined): FlowCategory | null {
  let best: FlowCategory | null = null
  for (const [c, v] of Object.entries(mix ?? {})) if ((v ?? 0) > (best ? mix?.[best] ?? 0 : 0)) best = c
  return best
}

const TREND_HOURS = 6
const HOUR = 3600

/** The last six hours of a service, oldest first, with 0 for an hour it had nothing. */
export function trendOf(s: FlowService, updated: number | undefined): { t: number; bytes: number }[] {
  const now = Math.floor((updated ?? Date.now() / 1000) / HOUR) * HOUR
  return Array.from({ length: TREND_HOURS }, (_, i) => {
    const t = now - (TREND_HOURS - 1 - i) * HOUR
    return { t, bytes: s.trend?.[String(t)] ?? 0 }
  })
}
