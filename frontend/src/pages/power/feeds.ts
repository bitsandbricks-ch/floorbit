import type { TFunction } from 'i18next'
import type { Circuit, CircuitFeedParts } from '@/api/types'

/** One feed as the plan names it: "B · row 2", "Block A", "Rows C–D" (issue #1427). */
export function feedText(t: TFunction, f: CircuitFeedParts): string {
  if (f.block === null) return t('powerFeeds.removed')
  const rows = f.rows.join(', ')
  if (f.by_rows) {
    // The block is named by its rows, so its rows are the hall's rows and it has no name of its own.
    return t('powerFeeds.hallRows', { count: f.rows.length || 2, rows: rows || f.block })
  }
  return f.rows.length ? t('powerFeeds.rows', { count: f.rows.length, block: f.block, rows }) : t('powerFeeds.block', { block: f.block })
}

/** Everything a circuit feeds, in the reader's language. */
export function feedsText(t: TFunction, c: Pick<Circuit, 'feeds_parts'>): string {
  return c.feeds_parts.map((f) => feedText(t, f)).join('; ')
}
