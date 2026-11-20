import { createContext } from 'react'
import type { Level } from './level'

/** In the dashboard editor, a widget tells its pane how it fits (issue #928): the level it drew at (and whether the box is too small even for that),
 *  and for a list how many of its rows show. Null everywhere else. */
export interface FitReport {
  /** ``tight``: the box is below what even small needs. */
  level: (level: Level, tight: boolean) => void
  rows: (shown: number, total: number) => void
}

/** How the picked pane draws, for the editor's settings panel (#928). ``rows``: shown and total for a cut list. */
export interface PaneFit {
  level: Level
  tight: boolean
  rows: [number, number] | null
}

export const LevelReport = createContext<FitReport | null>(null)
