import type { WalkHallRow } from '@/api/types'

type T = (k: string, o?: Record<string, unknown>) => string

/** A row as the crew say it: "Row C" for blocks named by their rows, else "Block A, row 1". */
export function rowTitle(t: T, r: Pick<WalkHallRow, 'name' | 'block_label' | 'naming'>) {
  return r.naming === 'rows' ? t('seatWalk.rowName', { name: r.name }) : t('seatWalk.blockRow', { block: r.block_label, name: r.name })
}
