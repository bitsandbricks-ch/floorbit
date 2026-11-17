import type { View } from './model'

/** Show the overview only once the plan is zoomed in far enough that part of it is off screen. */
export const MINIMAP_BELOW = 0.7

export function showMinimap(view: View, fit: View) {
  return view.w < fit.w * MINIMAP_BELOW || view.h < fit.h * MINIMAP_BELOW
}

/** The view centred on ``at`` (drawing units), same size: a click on the overview moves there. */
export function centreOn(view: View, at: { x: number; y: number }): View {
  return { ...view, x: at.x - view.w / 2, y: at.y - view.h / 2 }
}
