import { activeHref, group, INSIDE, isPluginPage, withParents, type NavPage } from './sections'

/** Where a path sits in the sidebar: its group and its page. */
export function crumbsFor(pages: NavPage[], path: string): { section: string | null; page: NavPage | null } {
  const lit = activeHref(pages, path)
  const found = pages.find((p) => p.href === lit) ?? null
  if (!found) return { section: null, page: null }
  // A tab of another page (Users in Settings) shows under that page.
  const page = found.id in INSIDE ? withParents(pages).find((p) => p.id === INSIDE[found.id]) ?? found : found
  if (isPluginPage(page.id)) return { section: 'plugins', page }
  const section = group(pages).sections.find((s) => s.pages.some((p) => p.href === page.href))?.id ?? null
  return { section, page }
}
