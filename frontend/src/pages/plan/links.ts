/** A seat or switch on the Seats page, which opens the hall it is in (issues #206, #228). Switches go by name. */
export function onPlan(place: { seat?: string | null; switch?: string | null }): string {
  return place.seat ? `/plan?seat=${encodeURIComponent(place.seat)}` : `/plan?switch=${encodeURIComponent(place.switch ?? '')}`
}
