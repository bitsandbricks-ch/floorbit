/** GET /api/settings/features (issue #114). */
export interface FeatureState {
  id: string
  on: boolean
  /** What the admin chose; a feature can still be off when one it needs is. */
  chosen: boolean
  forced_off: boolean
  needs: string[]
}
