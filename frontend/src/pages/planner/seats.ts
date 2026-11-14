/** "A-1 – A-46": a switch's seats are one run in the plan. */
export function seatRange(seats: string[]): string {
  if (seats.length === 0) return '–'
  return seats.length === 1 ? seats[0] : `${seats[0]} – ${seats[seats.length - 1]}`
}
