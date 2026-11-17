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
