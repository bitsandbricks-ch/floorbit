import { ActionIcon, UnstyledButton } from '@mantine/core'
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { State, Widget } from '@/api/types'
import { clock, dayClock } from '@/lib/time'
import type { Level } from '../level'
import { bucketsOf, formatValue, linesOf, PALETTE, type Part, partsOf } from './shape'
import { StatKind } from './Stat'

const COL_MIN = 28    // px per column: narrower can't be read or hovered
const LABEL_H = 18
const PAGER_H = 28

/** Vertical bars. Parts (states, a list's numbers) stand side by side with their label below;
 *  time data is cut into columns, each the average of its slice of time, one bar per line. */
export function ColumnsKind(props: { widget: Widget; level: Level; box: { w: number; h: number }; onMore?: () => void }) {
  const { widget, level, box } = props
  if (level === 's') return <StatKind widget={widget} level={level} box={box} />
  return widget.type === 'series' || widget.type === 'sparkline' ? <TimeColumns {...props} /> : <PartColumns {...props} />
}

function PartColumns({ widget, level, box, onMore }: { widget: Widget; level: Level; box: { w: number; h: number }; onMore?: () => void }) {
  const { t, i18n } = useTranslation()
  const [page, setPage] = useState(0)
  const parts = partsOf(widget, (s: State) => t(`widgets.state.${s}`), i18n.language)
  if (!parts.length) return <div className="fb-w-empty">{t('widgets.kind.noData')}</div>
  const room = Math.max(1, Math.floor(box.w / COL_MIN))
  const fit = parts.length > room ? Math.max(1, room - 1) : room
  const pages = level === 'l' ? Math.ceil(parts.length / fit) : 1
  const at = Math.min(page, pages - 1)
  const shown = parts.slice(at * fit, at * fit + fit)
  const more = level === 'l' ? 0 : parts.length - shown.length
  const top = Math.max(...parts.map((p) => p.max ?? p.value), 1)
  const plotH = box.h - LABEL_H - (pages > 1 ? PAGER_H : 0) - 16
  return (
    <div className="fb-w-cols-wrap">
      <div className="fb-w-cols" style={{ height: plotH + 16 + LABEL_H }}>
        {shown.map((p, i) => <Column key={i} part={p} top={top} h={plotH} />)}
        {more > 0 && (onMore
          ? <UnstyledButton className="fb-w-more fb-w-col-more" onClick={onMore}>{t('widgets.kind.more', { count: more })}</UnstyledButton>
          : <span className="fb-w-more fb-w-col-more">{t('widgets.kind.more', { count: more })}</span>)}
      </div>
      {pages > 1 && (
        <div className="fb-w-pager">
          <span>{t('widgets.kind.rowsOf', { from: at * fit + 1, to: at * fit + shown.length, count: parts.length })}</span>
          <ActionIcon size="sm" variant="subtle" color="gray" disabled={at === 0} aria-label={t('widgets.kind.prev')} onClick={() => setPage(at - 1)}><IconChevronLeft size={14} /></ActionIcon>
          <ActionIcon size="sm" variant="subtle" color="gray" disabled={at >= pages - 1} aria-label={t('widgets.kind.next')} onClick={() => setPage(at + 1)}><IconChevronRight size={14} /></ActionIcon>
        </div>
      )}
    </div>
  )
}

function Column({ part, top, h }: { part: Part; top: number; h: number }) {
  const full = part.max ?? top
  const pct = Math.min(100, (part.value / (full || 1)) * 100)
  const tip = part.max != null ? `${part.label}: ${part.text} (${Math.round(pct)} %)` : `${part.label}: ${part.text}`
  return (
    <div className="fb-w-col" title={tip}>
      <span className="fb-w-col-value">{part.max != null ? part.value : part.text}</span>
      <span className={`fb-w-col-track${part.max != null ? ' gauge' : ''}`} style={{ height: h }}>
        <span className="fb-w-col-fill" style={{ height: `${pct}%`, background: part.colour }} />
      </span>
      <span className="fb-w-col-label">{part.label}</span>
    </div>
  )
}

function TimeColumns({ widget, level, box }: { widget: Widget; level: Level; box: { w: number; h: number } }) {
  const { t, i18n } = useTranslation()
  const [hot, setHot] = useState<number | null>(null)
  const { lines, unit, timed } = linesOf(widget)
  const groupW = Math.max(6, lines.length * 6)
  const buckets = bucketsOf(lines, Math.max(1, Math.min(48, Math.floor(box.w / (groupW + 4)))))
  if (!buckets.length) return <div className="fb-w-empty">{t('widgets.kind.noData')}</div>
  const fmt = (v: number) => { const f = formatValue(v, unit, i18n.language); return `${f.value}${f.unit ? ` ${f.unit}` : ''}` }
  const span = buckets[buckets.length - 1].to - buckets[0].from
  const when = (ts: number) => (timed ? (span >= 86400 ? dayClock(ts * 1000) : clock(ts * 1000)) : '')
  const top = Math.max(1, ...buckets.flatMap((b) => b.values.map((v) => v ?? 0)))
  const W = box.w, H = Math.max(30, box.h - 20 - (level === 'l' ? 18 : 0))
  const slot = W / buckets.length
  const barW = Math.max(2, (slot - 3) / lines.length)
  const focus = hot != null ? buckets[hot] : null
  return (
    <div className="fb-w-graph">
      <div className="fb-w-legend">
        {lines.map((l, i) => <span key={i}><i style={{ background: PALETTE[i % PALETTE.length] }} />{l.label}</span>)}
      </div>
      <div className="fb-w-plot" onPointerLeave={() => setHot(null)}
        onPointerMove={(e) => setHot(Math.min(buckets.length - 1, Math.max(0, Math.floor((e.clientX - e.currentTarget.getBoundingClientRect().left) / slot))))}>
        <svg width={W} height={H} role="img" aria-label={t('widgets.kind.columnsLabel', { name: widget.label || lines.map((l) => l.label).join(', ') })}>
          <line className="fb-w-base" x1={0} x2={W} y1={H - 0.5} y2={H - 0.5} />
          {hot != null && <rect className="fb-w-col-hot" x={hot * slot} y={0} width={slot} height={H} />}
          {buckets.map((b, i) => b.values.map((v, li) => v == null ? null : (
            <rect key={`${i}-${li}`} x={i * slot + 1.5 + li * barW} width={barW} y={H - (v / top) * (H - 4)} height={(v / top) * (H - 4)}
              rx={1.5} fill={PALETTE[li % PALETTE.length]} />
          )))}
        </svg>
        {focus && (
          <div className="fb-w-tip" role="tooltip" style={{ left: Math.min(Math.max((hot! + 1) * slot + 6, 0), Math.max(0, W - 170)) }}>
            {timed && <div className="fb-w-tip-when">{`${when(focus.from)} – ${when(focus.to)}`}</div>}
            {lines.map((l, i) => (
              <div key={i}><i style={{ background: PALETTE[i % PALETTE.length] }} />{l.label}<b>{focus.values[i] == null ? '–' : fmt(focus.values[i]!)}</b></div>
            ))}
          </div>
        )}
      </div>
      {level === 'l' && (
        <div className="fb-w-axis"><span>{when(buckets[0].from)}</span><span>{t('widgets.kind.top', { value: fmt(top) })}</span><span>{when(buckets[buckets.length - 1].to)}</span></div>
      )}
    </div>
  )
}
