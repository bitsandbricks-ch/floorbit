/** GET /api/notice (issue #246): the lead's message to the whole crew. */
export interface CrewNotice {
  text: string
  level: 'info' | 'warn'
  /** Unix time it ends, or null: until a lead takes it down. */
  until: number | null
  by: string | null
  at: number
}
