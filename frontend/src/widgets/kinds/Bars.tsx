import { ActionIcon, UnstyledButton } from '@mantine/core'
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { State, Widget } from '@/api/types'
import { type Level, ROW_H, rowsThatFit } from '../level'
import { partsOf } from './shape'
import { StatKind } from './Stat'

/** Horizontal bars: how many in each state, or a list's numbers. Items with their own max (seats
 *  out of a block) fill a track, a bar gauge; otherwise bars share the biggest number's scale. */
export function BarsKind({ widget, level, box, onMore }: { widget: Widget; level: Level; box: { w: number; h: number }; onMore?: () => void }) {
  const { t, i18n } = useTranslation()
  const [page, setPage] = useState(0)
  if (level === 's') return <StatKind widget={widget} level={level} box={box} />
  const parts = partsOf(widget, (s: State) => t(`widgets.state.${s}`), i18n.language)
  if (!parts.length) return <div className="fb-w-empty">{t('widgets.kind.noData')}</div>
  const top = Math.max(...parts.map((p) => p.max ?? p.value), 1)
  const room = rowsThatFit(box.h)
  const fit = parts.length > room ? Math.max(1, room - 1) : room
  const pages = level === 'l' ? Math.ceil(parts.length / fit) : 1
  const at = Math.min(page, pages - 1)
  const shown = parts.slice(at * fit, at * fit + fit)
  const more = level === 'l' ? 0 : parts.length - shown.length
  const labelW = Math.min(160, Math.max(48, box.w * 0.28))
  return (
    <div className="fb-w-rows">
      <ul className="fb-w-bars" style={{ ['--label-w' as string]: `${labelW}px` }}>
        {shown.map((p, i) => {
          const full = p.max ?? top
          const pct = Math.min(100, (p.value / (full || 1)) * 100)
          const tip = p.max != null ? `${p.label}: ${p.text} (${Math.round(pct)} %)` : `${p.label}: ${p.text}`
          return (
            <li key={i} title={tip} style={{ height: ROW_H }}>
              <span className="fb-w-bar-label">{p.label}</span>
              <span className={`fb-w-bar-track${p.max != null ? ' gauge' : ''}`}>
                <span className="fb-w-bar-fill" style={{ width: `${pct}%`, background: p.colour }} />
              </span>
              <span className="fb-w-bar-value">{p.text}</span>
            </li>
          )
        })}
      </ul>
      {more > 0 && (onMore
        ? <UnstyledButton className="fb-w-more" onClick={onMore}>{t('widgets.kind.more', { count: more })}</UnstyledButton>
        : <span className="fb-w-more">{t('widgets.kind.more', { count: more })}</span>)}
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
