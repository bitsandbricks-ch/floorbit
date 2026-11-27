/** Pages Flask still draws itself: a full page load. Everything else in the list is a route of the
 *  React app, so the sidebar stays put and only the page changes. */
const SERVER_PAGES = new Set(['/', '/kiosk'])

export function isServerPage(href: string): boolean {
  const path = href.split(/[?#]/)[0]
  return SERVER_PAGES.has(path) || path.startsWith('/api/') || path.startsWith('/static/')
}

/** Can ``href`` open as a route of the React app? Not a page Flask draws, and not a big-screen or
 *  print view (the server picks their theme). With ``listed``, only pages in the sidebar's list. */
export function inApp(href: string, listed?: Set<string>): boolean {
  const url = new URL(href, 'http://x')
  if (isServerPage(url.pathname) || url.searchParams.has('screen') || url.searchParams.has('print')) return false
  return !listed || listed.has(url.pathname)
}
