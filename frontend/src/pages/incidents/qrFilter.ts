/** The block a seat belongs to: "D" for D-6, none for seats numbered without a block. */
export function seatBlock(seat: string): string {
  const cut = seat.lastIndexOf('-')
  return cut > 0 ? seat.slice(0, cut) : ''
}

/** Seat numbers typed by the crew, split on commas and spaces, compared like the help links (upper case). */
export function parseSeats(text: string): Set<string> {
  return new Set(text.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean))
}
