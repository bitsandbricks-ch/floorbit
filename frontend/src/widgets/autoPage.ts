import { createContext } from 'react'

/** Seconds a large list stays on one page before it turns to the next by itself: on a wall nobody
 *  clicks the pager (#925). 0 (the app) leaves paging to the viewer. */
export const AutoPage = createContext(0)

/** What a wall uses: long enough to read a page of names from across the hall. */
export const WALL_PAGE_SECONDS = 12
