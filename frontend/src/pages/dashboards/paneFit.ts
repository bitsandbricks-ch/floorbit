import type { Level } from '@bitsandbricks/widgets'

/** How the picked pane draws, for the editor's settings panel (#928). ``rows``: shown and total for a cut list.
 *  The widgets kit fills it through ``LevelReport`` but doesn't export the type yet (bitsandbricks-ch/ui). */
export interface PaneFit {
  level: Level
  tight: boolean
  rows: [number, number] | null
}
