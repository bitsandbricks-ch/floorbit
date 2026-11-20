import { createContext } from 'react'

/** In a large widget (#925), a row that names an inventory device opens its glance beside the
 *  widget. Null everywhere else: the dashboard itself, the editor and public walls. */
export const Drill = createContext<((device: string) => void) | null>(null)
