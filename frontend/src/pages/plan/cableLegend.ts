import type { PlanCable } from '@/api/types'

const MEDIA = ['copper', 'fiber', 'dac']

/** What the Network layer's seat cables show, for its legend: the media and speeds that are
 *  there (so the legend only explains what is on the plan) and how many cables were only read
 *  from the ports, not typed in. */
export function cableSummary(cables: PlanCable[]) {
  const lan = cables.filter((c) => c.kind === 'lan')
  const media = MEDIA.filter((m) => lan.some((c) => (c.media || 'copper') === m))
  const speeds = [...new Set(lan.map((c) => c.speed ?? 1))].sort((a, b) => a - b)
  return { total: lan.length, learned: lan.filter((c) => !c.ref.cable).length, media, speeds }
}
