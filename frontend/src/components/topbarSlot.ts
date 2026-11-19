import { createContext, useContext } from 'react'

/** The top bar's right side, where a page's buttons go on a computer (issue #932). AppShell
 *  provides it once the bar is drawn; outside the shell (tests, a panel) there is none. */
export const TopbarSlot = createContext<HTMLElement | null>(null)
export const useTopbarSlot = () => useContext(TopbarSlot)
