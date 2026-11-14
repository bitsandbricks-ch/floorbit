import type { FlowCategory, FlowMix } from '@/api/types'

export const CATEGORIES: FlowCategory[] = ['gaming', 'streaming', 'downloads', 'updates', 'web', 'other']

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
  return CATEGORIES.reduce((sum, c) => sum + (mix?.[c] ?? 0), 0)
}

/** The biggest category of a mix, for "mostly gaming". */
export function mostly(mix: FlowMix | undefined): FlowCategory | null {
  let best: FlowCategory | null = null
  for (const c of CATEGORIES) if ((mix?.[c] ?? 0) > (best ? mix?.[best] ?? 0 : 0)) best = c
  return best
}
