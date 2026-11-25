/** What one switch serves (GET /api/switch-areas, issue #948). */
export interface SwitchArea {
  name: string; id: string
  /** Where ``serves`` comes from: a pin, learned seats, the switch's place on the plan, or nothing yet. */
  how: 'manual' | 'learned' | 'plan' | 'todo' | 'excluded'
  serves: { blocks: string[]; rows: string[]; seats: string[] }
  manual: { blocks: string[]; rows: string[]; seats: string[]; exclude: boolean }
  learned: { seat: string; source: string }[]
  plan_blocks: string[]
  todo: boolean
  drift: { kind: 'learned_outside_pin' | 'learned_outside_plan' | 'drawn_elsewhere' | 'excluded_learned'; seats?: string[]; block?: string }[]
  suggest: { id: string; name: string; block_label: string }[]
}
export interface SwitchAreas { switches: SwitchArea[]; blocks: { id: string; label: string }[] }
