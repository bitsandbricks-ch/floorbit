import { createContext, useContext } from 'react'
import type { TimeRange } from './model'

/** Where a dashboard's panes read their data. Signed in: the usual API. A public dashboard on a screen
 *  nobody signed in to (``publicId``): its own feed, /api/dashboards/<id>/public/..., which hands out
 *  only what anyone may see (floorbit/dashboards.py public_board). ``hall``: the screen's ``?hall=``,
 *  for plan panes that don't name a hall of their own. */
export interface ScreenSource {
  publicId: string | null
  /** Tile names for the public feed (the tile list itself needs an account). */
  tiles: Record<string, string>
  hall: string
  /** The time the dashboard shows (its own, or the viewer's pick): panes without their own follow it. */
  range?: TimeRange
}

export const ScreenContext = createContext<ScreenSource>({ publicId: null, tiles: {}, hall: '' })

export const useScreen = () => useContext(ScreenContext)

export const publicUrl = (id: string, rest = '') => `/api/dashboards/${encodeURIComponent(id)}/public${rest}`

/** The next dashboard of ``?rotate=a,b,c`` after ``id``, for a screen that shows several in turn. */
export function nextInRotation(rotate: string | null, id: string): string | null {
  const ids = (rotate ?? '').split(',').map((x) => x.trim()).filter(Boolean)
  if (ids.length < 2) return null
  const at = ids.indexOf(id)
  return ids[(at + 1) % ids.length]
}
