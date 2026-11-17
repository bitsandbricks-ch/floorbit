import { createContext, useContext } from 'react'

/** Where a dashboard's panes read their data. Signed in: the usual API. A public dashboard on a screen
 *  nobody signed in to (``publicId``): its own feed, /api/dashboards/<id>/public/..., which hands out
 *  only what anyone may see (floorbit/dashboards.py public_board). ``hall``: the screen's ``?hall=``,
 *  for plan panes that don't name a hall of their own. */
export interface ScreenSource {
  publicId: string | null
  /** Tile names for the public feed (the tile list itself needs an account). */
  tiles: Record<string, string>
  hall: string
}

export const ScreenContext = createContext<ScreenSource>({ publicId: null, tiles: {}, hall: '' })

export const useScreen = () => useContext(ScreenContext)

export const publicUrl = (id: string, rest = '') => `/api/dashboards/${encodeURIComponent(id)}/public${rest}`
