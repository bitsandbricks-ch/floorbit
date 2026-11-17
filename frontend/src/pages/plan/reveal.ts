/** Scrolls a sideways-scrolling row (the seat filters on a phone) so its active item is in view,
 *  e.g. after opening /plan?show=recent, where the chosen filter starts off the screen. */
export function revealActive(row: HTMLElement | null, gap = 8) {
  const active = row?.querySelector<HTMLElement>('[data-active]')
  if (!row || !active) return
  const r = row.getBoundingClientRect()
  const a = active.getBoundingClientRect()
  if (a.right > r.right) row.scrollLeft += a.right - r.right + gap
  else if (a.left < r.left) row.scrollLeft -= r.left - a.left + gap
}
