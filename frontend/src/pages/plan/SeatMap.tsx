import { ActionIcon, Group, Tooltip } from '@mantine/core'
import { IconFocus2, IconMinus, IconPlus } from '@tabler/icons-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { PlanSeat, SeatViewData } from '@/api/types'
import { type Density, type Filter, type View, density, heatColor, heatLevel, matches, pan, parseBox, rate, scale, zoom } from './model'

/** One seat, in its block's coordinates. Every state has its own shape, not only its own colour:
 *  online is filled, offline is hollow with a slash, unknown is dashed. */
export function SeatGlyph({ seat, size, detail, traffic = false }: { seat: PlanSeat; size: number; detail: boolean; traffic?: boolean }) {
  const i = size * 0.08
  const s = size - 2 * i
  // With the traffic overlay an online seat is filled by its traffic; the shapes stay the same.
  const heat = traffic && seat.state === 'online' ? heatColor(heatLevel(seat.bps)) : undefined
  return (
    <>
      {seat.match && <rect className="match" x={i - 2.5} y={i - 2.5} width={s + 5} height={s + 5} rx={5} />}
      <rect className={`seat s-${seat.state}${heat ? ' heat' : ''}`} x={i} y={i} width={s} height={s} rx={3} style={heat ? { fill: heat } : undefined} />
      {seat.state === 'offline' && <line className="slash" x1={i + 4} y1={i + s - 4} x2={i + s - 4} y2={i + 4} />}
      {detail && seat.checked_in && <polygon className="chk" points={`${i + s * 0.42},${i} ${i + s},${i} ${i + s},${i + s * 0.58}`} />}
      {seat.problems ? (
        <g className="prob">
          <circle cx={i + 1} cy={i + 1} r={size * 0.24} />
          <text x={i + 1} y={i + 1} dy="0.35em">!</text>
        </g>
      ) : null}
    </>
  )
}

function useSize(ref: React.RefObject<HTMLElement | null>) {
  const [px, setPx] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => setPx({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return px
}

/** The plan with pan (drag, arrow keys), zoom (wheel, pinch, + and -) and three levels of detail. */
export function SeatMap({ data, selected, onSelect, filter, view, setView, traffic = false }: {
  data: SeatViewData; selected: string | null; onSelect: (seat: string) => void; filter: Filter
  view: View; setView: (v: View) => void; traffic?: boolean
}) {
  const { t } = useTranslation()
  const wrap = useRef<HTMLDivElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const px = useSize(wrap)
  const drawing = data.drawing!
  const fit = useMemo(() => parseBox(drawing.box), [drawing.box])
  const level: Density = density(drawing.cell, view, px)
  const s = scale(view, px) || 1
  const [hover, setHover] = useState<{ seat: string; x: number; y: number } | null>(null)
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const moved = useRef(false)

  // Screen point to plan point.
  const toPlan = (clientX: number, clientY: number) => {
    const el = svg.current
    const box = el?.getBoundingClientRect()
    if (!box || !box.width) return { x: view.x + view.w / 2, y: view.y + view.h / 2 }
    const k = Math.min(box.width / view.w, box.height / view.h)
    const ox = (box.width - view.w * k) / 2
    const oy = (box.height - view.h * k) / 2
    return { x: view.x + (clientX - box.left - ox) / k, y: view.y + (clientY - box.top - oy) / k }
  }
  const centre = () => ({ x: view.x + view.w / 2, y: view.y + view.h / 2 })

  // A wheel listener that may call preventDefault (React's is passive).
  const viewRef = useRef(view)
  useEffect(() => {
    viewRef.current = view
  }, [view])
  useEffect(() => {
    const el = svg.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const v = viewRef.current
      const box = el.getBoundingClientRect()
      const k = Math.min(box.width / v.w, box.height / v.h)
      const at = { x: v.x + (e.clientX - box.left - (box.width - v.w * k) / 2) / k, y: v.y + (e.clientY - box.top - (box.height - v.h * k) / 2) / k }
      setView(zoom(v, Math.exp(-e.deltaY * 0.0015), at, fit))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [fit, setView])

  const onPointerDown = (e: React.PointerEvent) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    moved.current = false
  }
  const onPointerMove = (e: React.PointerEvent) => {
    const p = pointers.current
    const last = p.get(e.pointerId)
    if (!last) return
    const k = scale(view, { w: svg.current?.clientWidth ?? 0, h: svg.current?.clientHeight ?? 0 }) || 1
    if (p.size === 1) {
      const dx = e.clientX - last.x
      const dy = e.clientY - last.y
      if (Math.abs(dx) + Math.abs(dy) > 3) moved.current = true
      if (moved.current) {
        svg.current?.setPointerCapture?.(e.pointerId)
        setView(pan(view, -dx / k, -dy / k))
      }
    } else if (p.size === 2) {
      const [a, b] = [...p.entries()]
      const other = a[0] === e.pointerId ? b[1] : a[1]
      const before = Math.hypot(last.x - other.x, last.y - other.y)
      const after = Math.hypot(e.clientX - other.x, e.clientY - other.y)
      moved.current = true
      if (before > 0) setView(zoom(view, after / before, toPlan((e.clientX + other.x) / 2, (e.clientY + other.y) / 2), fit))
    }
    p.set(e.pointerId, { x: e.clientX, y: e.clientY })
  }
  const onPointerUp = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId)
  }
  const onKey = (e: React.KeyboardEvent) => {
    const step = view.w * 0.1
    const moves: Record<string, () => View> = {
      '+': () => zoom(view, 1.25, centre(), fit), '=': () => zoom(view, 1.25, centre(), fit),
      '-': () => zoom(view, 0.8, centre(), fit), '0': () => fit,
      ArrowLeft: () => pan(view, -step, 0), ArrowRight: () => pan(view, step, 0),
      ArrowUp: () => pan(view, 0, -step), ArrowDown: () => pan(view, 0, step),
    }
    if (moves[e.key]) {
      e.preventDefault()
      setView(moves[e.key]())
    }
  }

  const stateText = (seat: PlanSeat) => [
    t(`plan.state.${seat.state}`),
    seat.checked_in ? t('plan.checkedIn') : null,
    seat.problems ? t('plan.problemsN', { count: seat.problems }) : null,
    seat.match ? t('plan.matchIn', { zone: seat.match }) : null,
    seat.bps ? rate(seat.bps) : null,
  ].filter(Boolean).join(' · ')

  const label = 14 / s   // block labels stay about 14 px tall at every zoom
  const tip = hover && data.seats[hover.seat]
  return (
    <div ref={wrap} className={`fb-plan-wrap d-${level}`}>
      <svg ref={svg} viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} className={traffic ? 'fb-plan traffic' : 'fb-plan'} tabIndex={0} role="application"
        aria-label={t('plan.mapLabel')} aria-roledescription={t('plan.mapRole')} onKeyDown={onKey}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
        onPointerLeave={() => setHover(null)}>
        {data.background && <image href={data.background} x={0} y={0} width={data.size.w} height={data.size.h} preserveAspectRatio="none" className="bg" />}
        {data.switches.map((w) => (
          <g key={w.id} className={`sw sw-${w.status}`} transform={`translate(${w.x} ${w.y})`}>
            <rect x={-7} y={-7} width={14} height={14} transform="rotate(45)" />
            <title>{`${w.name}: ${w.status}`}</title>
            {level === 'near' && <text y={22} fontSize={11}>{w.name}</text>}
          </g>
        ))}
        {drawing.shapes.map((b, bi) => (
          <g key={bi}>
            <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
              <rect className="blk" x={-b.w / 2 - 6} y={-b.h / 2 - 6} width={b.w + 12} height={b.h + 12} rx={8} />
              {b.cells.map((c) => {
                const seat = data.seats[c.seat] ?? { state: 'unknown' as const }
                const bright = traffic && seat.state === 'online' && heatLevel(seat.bps) > 0.6
                const cls = ['cell', matches(seat, filter) ? '' : 'dim', selected === c.seat ? 'sel' : '', bright ? 'bright' : ''].join(' ').trim()
                return (
                  <g key={c.seat} className={cls} data-seat={c.seat} data-state={seat.state} transform={`translate(${c.x} ${c.y})`}
                    role="button" aria-label={`${c.seat}: ${stateText(seat)}`}
                    onPointerEnter={(e) => {
                      const box = wrap.current?.getBoundingClientRect()
                      setHover({ seat: c.seat, x: e.clientX - (box?.left ?? 0), y: e.clientY - (box?.top ?? 0) })
                    }}
                    onPointerLeave={() => setHover(null)}
                    onClick={() => { if (!moved.current) onSelect(c.seat) }}>
                    <rect className="hit" width={drawing.cell} height={drawing.cell} />
                    <SeatGlyph seat={seat} size={drawing.cell} detail={level !== 'far'} traffic={traffic} />
                    {level === 'near' && (
                      <text className="num" x={drawing.cell / 2} y={drawing.cell / 2} dy="0.35em"
                        transform={b.rotation ? `rotate(${-b.rotation} ${drawing.cell / 2} ${drawing.cell / 2})` : undefined}>
                        {c.seat.split('-').pop()}
                      </text>
                    )}
                  </g>
                )
              })}
            </g>
            {b.name && level !== 'far' && <text className="name" x={b.cx} y={b.cy - Math.max(b.w, b.h) / 2 - 16} fontSize={Math.max(18, label)}>{b.name}</text>}
          </g>
        ))}
        {level === 'far' && drawing.shapes.map((b, bi) => {
          const sum = data.blocks.find((x) => x.name === b.name)
          if (!sum) return null
          return (
            <g key={`sum${bi}`} className="sum" transform={`translate(${b.cx} ${b.cy - Math.max(b.w, b.h) / 2 - 10})`} fontSize={label}>
              <text y={-label * 1.3}>{b.name}</text>
              <text y={-label * 0.2} className="sub">
                {sum.online}/{sum.seats}{sum.problems ? ` · ! ${sum.problems}` : ''}
              </text>
            </g>
          )
        })}
      </svg>
      {tip && hover && level !== 'far' && (
        <div className="fb-plan-tip" role="status" style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <b>{hover.seat}</b> {stateText(tip)}
        </div>
      )}
      <Group gap={4} className="fb-plan-zoom">
        <Tooltip label={t('plan.zoomIn')}><ActionIcon variant="default" aria-label={t('plan.zoomIn')} onClick={() => setView(zoom(view, 1.4, centre(), fit))}><IconPlus size={16} /></ActionIcon></Tooltip>
        <Tooltip label={t('plan.zoomOut')}><ActionIcon variant="default" aria-label={t('plan.zoomOut')} onClick={() => setView(zoom(view, 1 / 1.4, centre(), fit))}><IconMinus size={16} /></ActionIcon></Tooltip>
        <Tooltip label={t('plan.fit')}><ActionIcon variant="default" aria-label={t('plan.fit')} onClick={() => setView(fit)}><IconFocus2 size={16} /></ActionIcon></Tooltip>
      </Group>
    </div>
  )
}
