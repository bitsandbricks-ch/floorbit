import type { TFunction } from 'i18next'

// The titles the help page gives a seat's report (floorbit/incidents.py, report_from_seat). They are
// stored in English, so each reader sees them in their own language here.
const FROM_SEAT: Record<string, string> = {
  'No internet at the seat': 'noInternet',
  'Slow connection': 'slow',
  'No power at the seat': 'power',
  'Needs help at the seat': 'other',
}

// The titles a power alert gives its incident (floorbit/power.py), with the circuit's values in them.
const TRIPPED = /^Breaker tripped: (.+)$/
const LOAD = /^Circuit (.+) at (\d+(?:\.\d+)?) % of (\d+(?:\.\d+)?) A$/

export function incidentTitle(title: string, t: TFunction): string {
  const key = FROM_SEAT[title]
  if (key) return t(`incidents.seatTitle.${key}`)
  const tripped = TRIPPED.exec(title)
  if (tripped) return t('incidents.powerTitle.tripped', { name: tripped[1] })
  const load = LOAD.exec(title)
  if (load) return t('incidents.powerTitle.load', { name: load[1], pct: Number(load[2]), rating: Number(load[3]) })
  return title
}

// The note Floorbit writes on a power incident (floorbit/power.py): "Board DB-2, phase L3. Feeds 12 seats
// (C-13 to C-24) and switches sw-c-01." Anything else is the crew's own words and stays as written.
const NOTE = /^Board (.+?), phase (.+?)\.(?: Feeds (.+)\.)?$/
const SEATS = /^(\d+) seats \((.+) to (.+)\)$/

export function powerNote(text: string, t: TFunction): string {
  const m = NOTE.exec(text)
  if (!m) return text
  const head = t('incidents.powerNote.board', { board: m[1], phase: m[2] })
  if (!m[3]) return head
  const parts = m[3].split(' and ').map((part) => {
    const seats = SEATS.exec(part)
    if (seats) return t('incidents.powerNote.seats', { count: seats[1], first: seats[2], last: seats[3] })
    if (part.startsWith('seat ')) return t('incidents.powerNote.seat', { seat: part.slice(5) })
    if (part.startsWith('switches ')) return t('incidents.powerNote.switches', { names: part.slice(9) })
    return part
  })
  return `${head} ${t('incidents.powerNote.feeds', { what: parts.join(t('incidents.powerNote.and')) })}`
}
