/** Where a seat block's top edge is on screen once turned, in drawing units, so its name sits
 *  just above it (a long unturned row is wide, not tall). The 6 is the block outline's padding. */
export function blockTop(b: { cx: number; cy: number; w: number; h: number; rotation: number }) {
  const r = (b.rotation * Math.PI) / 180
  return b.cy - (Math.abs((b.w / 2) * Math.sin(r)) + Math.abs((b.h / 2) * Math.cos(r)) + 6)
}
