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

