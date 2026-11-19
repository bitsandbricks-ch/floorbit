import { createContext } from 'react'
import type { Level } from './level'

/** In the dashboard editor, a widget tells its pane which level it drew at, so the pane can show
 *  it while the box is resized (issue #928). Null everywhere else. */
export const LevelReport = createContext<((level: Level) => void) | null>(null)
