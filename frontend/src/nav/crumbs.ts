import { activeHref, group, isPluginPage, type NavPage } from './sections'

/** Where a path sits in the sidebar: its group and its page. */
export function crumbsFor(pages: NavPage[], path: string): { section: string | null; page: NavPage | null } {
  const lit = activeHref(pages, path)
  const page = pages.find((p) => p.href === lit) ?? null
  if (!page) return { section: null, page: null }
  if (isPluginPage(page.id)) return { section: 'plugins', page }
  const section = group(pages).sections.find((s) => s.pages.some((p) => p.href === page.href))?.id ?? null
  return { section, page }
}
