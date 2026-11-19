import { createContext } from 'react'
import type { Level } from './level'

/** In the dashboard editor, a widget tells its pane how it fits (issue #928): the level it drew at (and whether the box is too small even for that),
 *  and for a list how many of its rows show. Null everywhere else. */
export interface FitReport {
  /** ``tight``: the box is below what even small needs. */
  level: (level: Level, tight: boolean) => void
  rows: (shown: number, total: number) => void
}

export const LevelReport = createContext<FitReport | null>(null)
