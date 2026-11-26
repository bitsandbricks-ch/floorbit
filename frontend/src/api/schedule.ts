/** The event schedule (issue #106): talks, tournaments, meals and quiet hours. */
export type ScheduleKind = 'talk' | 'tournament' | 'meal' | 'quiet' | 'other'
export interface ScheduleItem {
  id: string
  title: string
  kind: ScheduleKind
  start: number
  end: number | null
  where: string
  note: string
  source: 'floorbit' | 'ical'
  uid: string | null
  updated_at: number | null
  by: string | null
}
export interface ScheduleData {
  event: { start: number | null; end: number | null }
  items: ScheduleItem[]
  kinds: ScheduleKind[]
}
