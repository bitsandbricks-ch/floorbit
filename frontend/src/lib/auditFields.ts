import type { TFunction } from 'i18next'

const PROBLEMS = new Set(['no-internet', 'slow', 'power', 'other'])

/** What an audit entry touched, for people: a changed setting by its label on the Settings page
 *  ("Stats wall", not ``public.stats_wall``); anything else as stored. */
export function fieldText(t: TFunction, area: string | undefined, field: string): string {
  if (area === 'settings') return t(`settings.fields.${field.replace(/\./g, '_')}.label`, { defaultValue: field })
  // A report from a seat names its problem by id ("slow"): say it as the help page does.
  if (area === 'incidents' && PROBLEMS.has(field)) return t(`seatHelp.problem.${field}`)
  return field
}

export function fieldsText(t: TFunction, area: string | undefined, fields: string[] | undefined): string {
  return (fields ?? []).map((f) => fieldText(t, area, f)).join(', ')
}
