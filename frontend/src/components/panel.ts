import { createContext, useContext } from 'react'

/** Set when a page is drawn inside another page's tab (the admin pages inside Settings): its
 *  Layout leaves the frame and the tab title to the outer page, and its PageHead is a section head. */
export const InPanel = createContext(false)

export const useInPanel = () => useContext(InPanel)
