export type SetupStep = 'netbox' | 'librenms' | 'switches' | 'theme'
export interface SetupState {
  needs_account: boolean
  done: boolean
  can_set_up?: boolean
  steps?: Partial<Record<SetupStep, 'done' | 'skipped'>>
  netbox?: boolean
  librenms?: boolean
  switches?: { total: number; placed: number }
  theme?: string
}
export interface ConnectionTest {
  ok: boolean
  message: string
}
