/** What the server asks the app to draw instead of the route's own page (floorbit/spa.py,
 *  ``spa.render(page=...)``): "not allowed", with the permission that was missing, or "not found". */
export interface ForbiddenPage { kind: 'forbidden'; permission: string; role: string }
/** A mistyped address, or a page whose feature is turned off (floorbit/not_found.py). */
export interface NotFoundPage { kind: 'not-found' }
export type ServerPage = ForbiddenPage | NotFoundPage

export function readServerPage(): ServerPage | null {
  const el = typeof document === 'undefined' ? null : document.getElementById('fb-page')
  if (!el?.textContent) return null
  try {
    const page = JSON.parse(el.textContent) as Partial<ServerPage>
    if (page.kind === 'not-found') return { kind: 'not-found' }
    if (page.kind === 'forbidden') return { kind: 'forbidden', permission: String(page.permission ?? ''), role: String(page.role ?? '') }
  } catch { /* a broken tag: draw the route as usual, its API calls answer 403 */ }
  return null
}
