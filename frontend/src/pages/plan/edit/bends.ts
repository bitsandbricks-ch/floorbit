import type { Point } from './geometry'

/** A cable's route as the editor changes it: its ends (fixed, at the switch and the seat) and the
 *  bends between, all in drawing units. The server keeps only the bends, in % of the plan. */
export type Route = Point[]

export const bendsOf = (route: Route) => route.slice(1, -1)

/** The middle of each stretch, where a new bend can be pulled out of it. */
export const midpoints = (route: Route) => route.slice(1).map((p, i) => ({ x: (route[i].x + p.x) / 2, y: (route[i].y + p.y) / 2 }))

/** ``route`` with bend ``i`` (counted among the bends) at ``to``. */
export const moveBend = (route: Route, i: number, to: Point): Route => route.map((p, k) => (k === i + 1 ? to : p))

/** ``route`` with a new bend at ``to`` in stretch ``i`` (between point ``i`` and ``i + 1``). */
export const addBend = (route: Route, i: number, to: Point): Route => [...route.slice(0, i + 1), to, ...route.slice(i + 1)]

export const removeBend = (route: Route, i: number): Route => route.filter((_, k) => k !== i + 1)

/** Bends on the plan's half-cell grid, or right where the pointer is (``free``, with Alt). */
export const snapBend = (p: Point, cell: number, free: boolean): Point =>
  (free ? p : { x: Math.round(p.x / (cell / 2)) * (cell / 2), y: Math.round(p.y / (cell / 2)) * (cell / 2) })

/** The bends as the server keeps them: % of the plan, two decimals. */
export const bendsPct = (route: Route, size: { w: number; h: number }): [number, number][] =>
  bendsOf(route).map((p) => [Math.round((p.x / size.w) * 10000) / 100, Math.round((p.y / size.h) * 10000) / 100])
