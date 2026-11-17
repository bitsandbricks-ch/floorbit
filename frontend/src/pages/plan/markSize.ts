import type { PlanMark } from '@/api/types'

// Label and icon sizes in drawing units (the plan is 1600 wide, a seat 32).
const TEXT = { s: 20, m: 28, l: 44 }
const ICON = { s: 26, m: 36, l: 52 }
export const SCALE_MIN = 0.25
export const SCALE_MAX = 8

/** A label's font size or an icon's square, in drawing units: its size step times its scale. */
export const markPx = (m: Pick<PlanMark, 'kind' | 'size' | 'scale'>) =>
  (m.kind === 'icon' ? ICON : TEXT)[m.size ?? 'm'] * (m.scale ?? 1)
