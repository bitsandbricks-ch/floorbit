import { useSyncExternalStore } from 'react'
const STEPS = [1, 2, 5, 10, 20, 50, 100, 200]

/** How wide a ruler is, in screen pixels. */
export const RULER_BAND = 18

/** Which seat counts get a number on a ruler: the smallest step that leaves ``gap`` screen pixels
 *  between the numbers, and the ticks between them. */
export function rulerSteps(cellPx: number, gap = 60): { major: number; minor: number } {
  const major = STEPS.find((s) => s * cellPx >= gap) ?? STEPS[STEPS.length - 1]
  const minor = [major / 10, major / 5, major / 2, major].find((m) => Number.isInteger(m) && m * cellPx >= 8) ?? major
  return { major, minor }
}


/** Where the pointer is on the plan (plan units), for the rulers' marker. Kept outside React state
 *  so a mouse move redraws only the rulers, not the editor. */
let pointerAt: { x: number; y: number } | null = null
const pointerListeners = new Set<() => void>()
export function setRulerPointer(at: { x: number; y: number } | null) {
  if (at === pointerAt || (at && pointerAt && at.x === pointerAt.x && at.y === pointerAt.y)) return
  pointerAt = at
  pointerListeners.forEach((l) => l())
}
export function useRulerPointer() {
  return useSyncExternalStore((l) => { pointerListeners.add(l); return () => pointerListeners.delete(l) }, () => pointerAt)
}

/** A position in seats for a ruler's readout: one decimal, no trailing ".0". */
export function seatsLabel(units: number, cell: number): string {
  return String(Math.round((units / cell) * 10) / 10)
}
