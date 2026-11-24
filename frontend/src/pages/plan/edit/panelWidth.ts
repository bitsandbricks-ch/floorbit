import { useState } from 'react'

const KEY = 'floorbit.editPanelWidth'
export const PANEL_MIN = 320
export const PANEL_MAX = 720

function read(): number | null {
  try {
    const n = Number(localStorage.getItem(KEY))
    return Number.isFinite(n) && n >= PANEL_MIN && n <= PANEL_MAX ? n : null
  } catch {
    return null
  }
}

/** The edit panel's width when someone dragged its edge, remembered in this browser; null keeps the
 *  default (440 px, 520 px on wide screens, plan-frame.css). */
export function usePanelWidth() {
  const [width, setWidth] = useState<number | null>(read)
  const save = (w: number | null) => {
    setWidth(w)
    try { if (w == null) localStorage.removeItem(KEY); else localStorage.setItem(KEY, String(w)) } catch { /* private window: this visit only */ }
  }
  return [width, save] as const
}
