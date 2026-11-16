import type { PlanBlock as Block } from '@/api/types'

/** The blocks a big screen points out: the ones with problems, most first, at most ``max``. */
export function troubleBlocks(blocks: Block[], max = 6): { shown: Block[]; more: number } {
  const bad = blocks.filter((b) => b.problems > 0)
    .sort((a, b) => b.problems - a.problems || a.name.localeCompare(b.name, undefined, { numeric: true }))
  return { shown: bad.slice(0, max), more: Math.max(0, bad.length - max) }
}
