import type { TFunction } from 'i18next'

// The titles the help page gives a seat's report (floorbit/incidents.py, report_from_seat). They are
// stored in English, so each reader sees them in their own language here.
const FROM_SEAT: Record<string, string> = {
  'No internet at the seat': 'noInternet',
  'Slow connection': 'slow',
  'No power at the seat': 'power',
  'Needs help at the seat': 'other',
}

export function incidentTitle(title: string, t: TFunction): string {
  const key = FROM_SEAT[title]
  return key ? t(`incidents.seatTitle.${key}`) : title
}
