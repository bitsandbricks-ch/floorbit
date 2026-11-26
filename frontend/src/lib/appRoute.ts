import type { ReactElement } from 'react'

/** One address of the React app. Each area lists its own in src/routes/<area>.ts and App.tsx
 *  collects every file there (issue #1234), so a new page doesn't add a line to a shared list. */
export interface AppRoute {
  path: string
  element: ReactElement
  /** false: the page alone, without the sidebar and top bar (sign-in, a dashboard on a big screen). */
  shell?: boolean
}
