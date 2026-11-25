import type { Board } from './model'

export type Show = 'all' | 'pinned' | 'mine' | 'readyMade' | 'public' | 'plugins'
export const SHOWS: Show[] = ['all', 'pinned', 'mine', 'readyMade', 'public', 'plugins']

/** Which dashboards the "Show" filter keeps. */
export function shows(b: Board, show: Show, ctx: { pinned: (id: string) => boolean; me?: string | null }): boolean {
  switch (show) {
    case 'pinned': return ctx.pinned(b.id)
    case 'mine': return !!ctx.me && b.by === ctx.me
    case 'readyMade': return !!(b.builtin || b.changed)
    case 'public': return !!b.public
    case 'plugins': return !!b.plugin
    default: return true
  }
}

/** The text search: the name (in this language), its tags and its group. */
export function matches(b: Board, search: string, name: string): boolean {
  const q = search.trim().toLowerCase()
  if (!q) return true
  return [name, b.id, b.group ?? '', ...(b.tags ?? [])].some((x) => x.toLowerCase().includes(q))
}
