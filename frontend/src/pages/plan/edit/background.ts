import type { Box, Point } from './geometry'

type Size = { w: number; h: number }

/** A background frame in drawing units as the server keeps it: % of the plan. */
export function framePct(f: Box, size: Size): Box {
  const r = (n: number) => Math.round(n * 1000) / 1000
  return { x: r((f.x / size.w) * 100), y: r((f.y / size.h) * 100), w: r((f.w / size.w) * 100), h: r((f.h / size.h) * 100) }
}

/** ``f`` scaled by ``k`` round ``about``, which stays where it is on the drawing. */
export function scaleFrame(f: Box, about: Point, k: number): Box {
  return { x: about.x - (about.x - f.x) * k, y: about.y - (about.y - f.y) * k, w: f.w * k, h: f.h * k }
}

/** Calibrating with a line ``seats`` long on the plan that is ``metres`` long for real:
 *  how many metres one seat is. */
export function seatMetres(seats: number, metres: number): number {
  return Math.round((metres / seats) * 1000) / 1000
}

/** How much to scale the background so a line ``seats`` long on it becomes ``metres`` long at
 *  ``seatM`` metres per seat. */
export function fitFactor(seats: number, metres: number, seatM: number): number {
  return metres / seatM / seats
}
