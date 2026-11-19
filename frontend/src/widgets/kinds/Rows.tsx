import { TextInput, UnstyledButton } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Widget } from '@/api/types'
import { DataTable, type DataColumn } from '@/components/DataTable'
import { type Kind, type Level, ROW_H, rowsThatFit } from '../level'
import { type Row, rowsOf, stateCounts, statOf } from './shape'

const BAR_H = 34

/** Status, list and table: the rows that fit, never a scrollbar. Medium ends in "+N more" (which
 *  opens the widget large); large pages, sorts and filters inside the box. */
export function RowsKind({ widget, kind, level, box, onMore }: {
  widget: Widget; kind: Kind; level: Level; box: { w: number; h: number }; onMore?: () => void
}) {
  const { t, i18n } = useTranslation()
  const { columns, rows } = useMemo(() => rowsOf(widget, {
    name: t('widgets.kind.name'), value: t('widgets.kind.value'), state: t('widgets.kind.detail'),
  }), [widget, t])
  const [query, setQuery] = useState('')

  if (level === 's') {
    const s = statOf(widget, i18n.language)
    const counts = stateCounts(widget)
    return (
      <div className="fb-w-stat">
        <div className="fb-w-stat-main">
          <span className={`fb-w-stat-value${s.tone ? ` fb-tone-${s.tone}` : ''}`}>{s.value}</span>
          {s.of != null && <span className="fb-w-stat-unit">{t('widgets.kind.of', { count: s.of })}</span>}
        </div>
        {counts.length > 1 && (
          <div className="fb-w-counts">
            {counts.filter(([st]) => st !== 'up').map(([st, n]) => (
              <span key={st}><span className={`fb-dot ${st}`} role="img" aria-label={t(`widgets.state.${st}`)} /> {n}</span>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (!rows.length) return <div className="fb-w-empty">{t('widgets.kind.noRows')}</div>

  const table = kind === 'table'
  const big = level === 'l'
  const filtering = big && (rows.length > rowsThatFit(box.h, ROW_H) || query !== '')
  let shown: Row[] = rows
  if (query) {
    const q = query.toLowerCase()
    shown = shown.filter((r) => Object.values(r.cells).some((v) => String(v ?? '').toLowerCase().includes(q)))
  }
  const reserve = (table ? ROW_H : 0) + (filtering ? BAR_H : 0)
  const room = rowsThatFit(box.h, reserve)
  // When not all rows fit, one row's height goes to "+N more" (medium) or the pager (large).
  const fit = shown.length > room ? Math.max(1, room - 1) : room
  // Medium shows what fits, worst first; large pages and sorts the rest inside the box.
  const slice = big ? shown : shown.slice(0, fit)
  const more = big ? 0 : shown.length - slice.length

  const cols: DataColumn<Row>[] = (table ? columns : columns.slice(0, 2)).map((c, j) => ({
    id: c.key,
    header: c.label,
    sort: big && table ? (r) => r.cells[c.key] ?? '' : undefined,
    className: j > 0 && !table ? 'fb-w-side' : undefined,
    cell: (r) => {
      const v = r.cells[c.key] ?? ''
      return (
        <span title={v || undefined} className={j > 0 && !table && r.tone ? `fb-tone-${r.tone}` : undefined}>
          {j === 0 && r.state && <span className={`fb-dot ${r.state}`} role="img" aria-label={t(`widgets.state.${r.state}`)} title={t(`widgets.state.${r.state}`)} />}
          {v}
        </span>
      )
    },
  }))
  return (
    <div className="fb-w-rows">
      {filtering && (
        <TextInput size="xs" leftSection={<IconSearch size={14} />} placeholder={t('widgets.kind.filter')} aria-label={t('widgets.kind.filter')}
          value={query} onChange={(e) => setQuery(e.currentTarget.value)} className="fb-w-filter" />
      )}
      {/* Keyed by the filter, so a new filter starts on the first page. */}
      <DataTable key={query} rows={slice} columns={cols} rowKey={(_, i) => String(i)} label={widget.label}
        urlState={false} pageSize={big ? fit : 0} bare head={table} pager="compact" density="compact"
        className={`fb-w-table${table ? '' : ' fb-w-plain'}`} empty={<div className="fb-w-empty">{t('widgets.kind.noRows')}</div>} />
      {more > 0 && (
        onMore
          ? <UnstyledButton className="fb-w-more" onClick={onMore}>{t('widgets.kind.more', { count: more })}</UnstyledButton>
          : <span className="fb-w-more">{t('widgets.kind.more', { count: more })}</span>
      )}
    </div>
  )
}
