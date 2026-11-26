/** Pre-flight check board (issue #35). */
export type PreflightStatus = 'pass' | 'warn' | 'fail' | 'skip'
export type PreflightGroupId = 'switches' | 'uplinks' | 'services'
export interface PreflightItem { id: string; name: string; status: PreflightStatus; detail: string; switch_id?: string; kind?: string }
export interface PreflightGroup { at: number; by: string | null; items: PreflightItem[] }
export interface PreflightBoard {
  groups: Record<PreflightGroupId, PreflightGroup | null>
  counts: Record<PreflightStatus, number>
  ready: boolean; complete: boolean
}
