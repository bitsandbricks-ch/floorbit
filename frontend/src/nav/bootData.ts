/** The JSON the server puts into the page for the sidebar (templates/_nav.html), unparsed into
 *  types. A module of its own so the pages outside the shell can read the brand without loading
 *  the sidebar's sections and their icons (issue #1293). */
export function readNavData(): Record<string, unknown> {
  const el = typeof document === 'undefined' ? null : document.getElementById('fb-nav-data')
  if (!el?.textContent) return {}
  try {
    const v: unknown = JSON.parse(el.textContent)
    return v && typeof v === 'object' ? (v as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

export interface Brand { logo: string | null; name: string | null }

/** The event's logo and name, as the sidebar shows them. */
export function readBrand(): Brand {
  const b = readNavData().brand as Partial<Brand> | undefined
  return { logo: b?.logo ?? null, name: b?.name ?? null }
}
