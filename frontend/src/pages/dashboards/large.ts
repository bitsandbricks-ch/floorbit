import { createContext, useCallback, useContext } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { Section } from './grid'
import { at, isPane, type Pane, type Path } from './model'

/** "Make large" (issue #925): a pane opens over the whole dashboard area instead of a dialog. The
 *  address holds it (``?w=<section>.<panel>[.<path>]``), so Back and a shared link work. */

/** Which pane this is on its dashboard, so its "make large" button can name it in ``?w=``. */
export const PaneKey = createContext<string | null>(null)

/** True inside the large view: the pane draws at its large level and has no button to open it again. */
export const LargeContext = createContext(false)

export const paneKey = (section: number, panel: number, path: Path = []) => [section, panel, ...path].join('.')

/** The pane ``key`` names, or null when it's gone (the dashboard changed since the link was made). */
export function paneAt(sections: Section[], key: string): Pane | null {
  const [s, p, ...path] = key.split('.').map(Number)
  if ([s, p, ...path].some((n) => !Number.isInteger(n) || n < 0)) return null
  const root = sections[s]?.panels[p]?.node
  const node = root && at(root, path)
  return node && isPane(node) ? node.pane : null
}

/** The open large pane's key, and how to open or close it. Opening adds a history entry, so the
 *  browser's Back closes it too. */
export function useLarge(): { open: string | null; show: (key: string) => void; close: () => void } {
  const [params, setParams] = useSearchParams()
  const open = params.get('w')
  const show = useCallback((key: string) => setParams((p) => { const n = new URLSearchParams(p); n.set('w', key); return n }), [setParams])
  const close = useCallback(() => setParams((p) => { const n = new URLSearchParams(p); n.delete('w'); return n }, { replace: true }), [setParams])
  return { open, show, close }
}

/** The opener a pane's button and "+N more" call; null outside a dashboard (the editor, a test). */
export function useMakeLarge(): (() => void) | null {
  const key = useContext(PaneKey)
  const large = useContext(LargeContext)
  const { show } = useLarge()
  return key && !large ? () => show(key) : null
}
