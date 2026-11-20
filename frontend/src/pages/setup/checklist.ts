import { useQuery } from '@tanstack/react-query'
import { get } from '@/api/client'
import { qk } from '@/api/keys'

export type StepState = 'done' | 'look' | 'todo' | 'skipped'
export type ChecklistStep = { id: string; state: StepState; href: string; facts: Record<string, number | boolean> }
export type Checklist = { steps: ChecklistStep[]; done: boolean }

export const checklistKey = [...qk.setup, 'checklist']

/** GET /api/setup/checklist: what the event still needs (#988). */
export function useChecklist(enabled = true) {
  return useQuery({ queryKey: checklistKey, queryFn: () => get<Checklist>('/api/setup/checklist'), enabled })
}
