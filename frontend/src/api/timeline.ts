/** Event changelog (issue #100). */
export type TimelineKind = 'change' | 'sign-in' | 'outage' | 'incident' | 'alert' | 'deploy'
export interface TimelineEntry {
  t: number; kind: TimelineKind; title: string; target?: string; who?: string; area?: string
  /** What a change touched, as stored (setting keys for settings): see lib/auditFields.ts. */
  fields?: string[]
  severity?: 'up' | 'down' | 'warn' | 'info'; version?: string; id?: string
}
export interface TimelineData { entries: TimelineEntry[]; total: number; counts: Record<TimelineKind, number>; kinds: TimelineKind[]; more: boolean }
