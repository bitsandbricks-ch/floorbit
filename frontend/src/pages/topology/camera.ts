/** Pan and zoom for the topology diagram: the camera is the SVG's viewBox. Zooming keeps the
 *  camera's shape, so the SVG's height (auto, from the viewBox) doesn't jump while zooming. */
export interface Box { x: number; y: number; w: number; h: number }

export const MIN_ZOOM = 0.35 // of the whole picture: 3x wider than it is
export const MAX_ZOOM = 8

/** Zoom by `factor` (>1 closer) around a point in diagram units, kept between the limits. */
export function zoomAt(cam: Box, base: Box, factor: number, at: { x: number; y: number }): Box {
  const w = Math.min(base.w / MIN_ZOOM, Math.max(base.w / MAX_ZOOM, cam.w / factor))
  const h = (w * cam.h) / cam.w
  const k = w / cam.w
  return { x: at.x - (at.x - cam.x) * k, y: at.y - (at.y - cam.y) * k, w, h }
}

/** A point on screen (client pixels) in diagram units, for an element showing `cam`. */
export function toDiagram(cam: Box, rect: { left: number; top: number; width: number; height: number }, clientX: number, clientY: number) {
  return { x: cam.x + ((clientX - rect.left) / (rect.width || 1)) * cam.w, y: cam.y + ((clientY - rect.top) / (rect.height || 1)) * cam.h }
}

/** The box around everything drawn, with a margin. */
export function bounds(points: { x: number; y: number; w: number; h: number }[], margin = 10): Box {
  if (!points.length) return { x: -margin, y: -margin, w: 2 * margin, h: 2 * margin }
  const x0 = Math.min(...points.map((p) => p.x)), y0 = Math.min(...points.map((p) => p.y))
  const x1 = Math.max(...points.map((p) => p.x + p.w)), y1 = Math.max(...points.map((p) => p.y + p.h))
  return { x: x0 - margin, y: y0 - margin, w: x1 - x0 + 2 * margin, h: y1 - y0 + 2 * margin }
}
