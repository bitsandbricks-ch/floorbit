import { PlanMarks } from './PlanMarks'
import { ActionIcon, Group, Tooltip, VisuallyHidden } from '@mantine/core'
import { IconFocus2, IconMinus, IconPlus } from '@tabler/icons-react'
import { memo, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { FirewallSeats, IncidentMarkers, PlanCable, PlanSeat, PluginLayerData, PluginLayerTone, PowerMarkers, SeatViewData, WifiData } from '@/api/types'
import {
  type Density, type Direction, type Filter, type View, density, heatColor, heatLevel, matches, minutesAgo, nearestSeat, nextSeat, pan,
  parseBox, rate, reveal, scale, seatCenter, zoom,
} from './model'
import { DEFAULT_LAYERS, type LayerState, layerStyle, opacity } from './layers'
import { CableLines, CablePlugs, PanelGlyphs } from './NetworkLayer'
import { followPlan } from './cableRoute'
import { PowerLayer } from './PowerLayer'
import { blockAlarm } from './blockTop'
import { blockSums, placeLabels, placesAround, shapeLabel, shapeRect, textWidth } from './blockSums'
import { Minimap } from './Minimap'
import { useSize } from './useSize'
import { showMinimap } from './minimap'
import { WifiLayer } from './WifiLayer'
import { type LabelMode, type SeatLabels, labelPlan, labelStyle, rowEnds } from './labels'
import { UPLINK_WIDTH } from './linkLook'

/** One seat, in its block's coordinates. Every state has its own shape, not only its own colour:
 *  online is filled, offline is hollow with a slash, unknown is dashed. */
export function SeatGlyph({ seat, size, detail, traffic = false, route, checkin = true, incidents = 0, mark }: {
  seat: PlanSeat; size: number; detail: boolean; traffic?: boolean
  /** A plugin layer's tone for this seat (./PluginLayer.tsx): a coloured ring. */
  mark?: PluginLayerTone
  /** Draw the check-in corner (the check-in layer). */
  checkin?: boolean
  /** Open incidents at the seat (the crew layer). */
  incidents?: number
  /** With the firewall layer: the seat's traffic failed over (dashed ring) or has no firewall left (solid ring). */
  route?: 'failover' | 'down'
}) {
  const i = size * 0.08
  const s = size - 2 * i
  // With the traffic overlay an online seat is filled by its traffic; the shapes stay the same.
  const heat = traffic && seat.state === 'online' ? heatColor(heatLevel(seat.bps)) : undefined
  return (
    <>
      {seat.changed && <rect className="recent" x={i - 5} y={i - 5} width={s + 10} height={s + 10} rx={7} />}
      {mark && <rect className={`pl pl-${mark}`} x={i - 3.5} y={i - 3.5} width={s + 7} height={s + 7} rx={6} />}
      {route && <rect className={`fwr fw-${route}`} x={i - 3.5} y={i - 3.5} width={s + 7} height={s + 7} rx={6} />}
      <rect className={`seat s-${seat.state}${heat ? ' heat' : ''}`} x={i} y={i} width={s} height={s} rx={3} style={heat ? { fill: heat } : undefined} />
      {seat.state === 'offline' && <line className="slash" x1={i + 4} y1={i + s - 4} x2={i + s - 4} y2={i + 4} />}
      {detail && seat.note && <polygon className="note" points={`${i},${i + s * 0.58} ${i + s * 0.42},${i + s} ${i},${i + s}`} />}
      {detail && checkin && seat.checked_in && <polygon className="chk" points={`${i + s * 0.42},${i} ${i + s},${i} ${i + s},${i + s * 0.58}`} />}
      {incidents > 0 && (
        <g className="inc">
          <circle cx={i + s - 1} cy={i + 1} r={size * 0.24} />
          <text x={i + s - 1} y={i + 1} dy="0.35em">{incidents > 9 ? '9+' : incidents}</text>
        </g>
      )}
      {seat.problems ? (
        <g className="prob">
          <circle cx={i + 1} cy={i + 1} r={size * 0.24} />
          <text x={i + 1} y={i + 1} dy="0.35em">!</text>
        </g>
      ) : null}
    </>
  )
}

// The editor's grid steps, in % of the plan, so things sit on the same lines.
const GRID_STEPS = [0.5, 1, 2.5, 5, 10, 25, 50]
const GRID_MIN_PX = 12

/** The editor's grid under the plan: the finest step that stays ``GRID_MIN_PX`` apart on screen, a
 *  stronger line two steps up. Only the lines in ``view`` (what the screen shows) are drawn. */
export function PlanGrid({ view, size, scale: k }: { view: View; size: { w: number; h: number }; scale: number }) {
  const perPct = (Math.min(size.w, size.h) / 100) * k
  if (!perPct) return null
  let i = GRID_STEPS.findIndex((step) => step * perPct >= GRID_MIN_PX)
  if (i < 0) i = GRID_STEPS.length - 1
  const minor = GRID_STEPS[i], major = GRID_STEPS[Math.min(i + 2, GRID_STEPS.length - 1)]
  const lines: React.ReactNode[] = []
  const axis = (from: number, span: number, unit: number, vertical: boolean) => {
    const step = minor * unit
    for (let n = Math.floor(from / step); n * step <= from + span; n++) {
      const at = n * step
      const strong = Math.abs(at / (major * unit) - Math.round(at / (major * unit))) < 1e-6
      lines.push(vertical
        ? <line key={`v${n}`} className={strong ? 'major' : undefined} x1={at} y1={view.y} x2={at} y2={view.y + view.h} />
        : <line key={`h${n}`} className={strong ? 'major' : undefined} x1={view.x} y1={at} x2={view.x + view.w} y2={at} />)
    }
  }
  axis(view.x, view.w, size.w / 100, true)
  axis(view.y, view.h, size.h / 100, false)
  return <g className="fb-grid" aria-hidden="true">{lines}</g>
}

/** A switch seen from the front, centred on its spot (the editor draws the same):
 *  lit ports when online, a cross when offline, a dashed box when unknown. */
export function SwitchGlyph({ status }: { status: string }) {
  const lit = status === 'online' || status === 'warning'
  return (
    <>
      <rect className="body" x={-12} y={-8} width={24} height={16} rx={3} />
      {status === 'offline'
        ? <path className="cross" d="M-3.5 -4.5l7 9M3.5 -4.5l-7 9" />
        : [0, 1].flatMap((row) => [0, 1, 2, 3, 4].map((i) => (
          <rect key={`${row}-${i}`} className={lit ? 'port lit' : 'port'} x={-8.8 + i * 3.7} y={-3.6 + row * 4} width={2.5} height={2.4} rx={0.4} />
        )))}
    </>
  )
}

const ARROWS: Record<string, Direction> = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' }

/** The plan with pan (drag, Shift + arrow keys), zoom (wheel, pinch, + and -) and three levels of
 *  detail. Arrow keys move a cursor from seat to seat and Enter opens it (issue #155). */
const ALL_DEFAULT: LayerState = { on: new Set(DEFAULT_LAYERS), fade: {} }

/** What an overlay drawn over the plan (the editor's selection and handles) needs to know. */
export interface OverlayContext {
  /** Screen point to plan point. */
  toPlan: (clientX: number, clientY: number) => { x: number; y: number }
  /** Screen pixels per drawing unit. */
  scale: number
  /** What the screen shows, in drawing units (wider than ``view`` when the screen's shape differs). */
  shown: View
}

export function SeatMap({ data, selected, onSelect, onClear, onBlock, onSwitch, filter, view, setView, traffic = false, power, firewalls, level: forced,
  layers = ALL_DEFAULT, wifi, incidents, cables, overlay, focus, labels: labelMode = 'auto', pluginSeats, rings = false }: {
  /** An open switch panel: only that switch's seats stay bright, and the switch gets a ring. An
   *  open seat: its switch gets the ring and a line from the seat (``seat``), nothing is dimmed. An
   *  open block: only ``seats``. */
  focus?: { switch?: string; seats?: ReadonlySet<string>; seat?: string }
  data: SeatViewData; selected: string | null; onSelect: (seat: string) => void; onClear?: () => void
  onBlock?: (block: string) => void; onSwitch?: (name: string) => void; filter: Filter
  view: View; setView: (v: View) => void; traffic?: boolean
  /** The power layer (issue #468): boards and cables, drawn under the switches. */
  power?: PowerMarkers
  /** The firewall layer (issue #470): seats not on their planned firewall. */
  firewalls?: FirewallSeats['seats']
  /** Force a detail level, e.g. 'near' on paper where screen pixels mean nothing. */
  level?: Density
  /** Which layers are on and how strong (./layers.ts); the switches, labels and check-in corners by default. */
  layers?: LayerState
  /** The Wi-Fi layer: access points of this hall. */
  wifi?: WifiData
  /** The crew layer: open incidents per seat and switch. */
  incidents?: IncidentMarkers
  /** Seat cables on the Network layer (Network and Edit modes; GET /api/cable-plan). */
  cables?: PlanCable[]
  /** Drawn over everything and given the pointer first (the editor, pages/plan/edit/). */
  overlay?: (ctx: OverlayContext) => React.ReactNode
  /** Seat numbers: follow the zoom (./labels.ts), or always / never, for a big screen. */
  labels?: LabelMode
  /** The plugin layer that is on: a tone per seat. */
  pluginSeats?: PluginLayerData['seats']
  /** A ring that stays a few pixels wide around every seat with a problem, so one red seat in a
   *  hall of hundreds still shows on a big screen. */
  rings?: boolean
}) {
  const { t } = useTranslation()
  const ids = useId().replace(/:/g, '')
  const wrap = useRef<HTMLDivElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const px = useSize(wrap)
  const drawing = data.drawing!
  const fit = useMemo(() => parseBox(drawing.box), [drawing.box])
  const level: Density = forced ?? density(drawing.cell, view, px)
  const s = scale(view, px) || 1
  // Paper ('near' forced) numbers every seat at the classic size; screens follow the zoom.
  const named = forced === 'near' ? labelPlan(drawing.cell, 2, labelMode) : labelPlan(drawing.cell, scale(view, px) || 0.75, labelMode)
  const seatLabels: SeatLabels = level === 'far' && labelMode !== 'all' ? 'none' : named.seats
  const [hover, setHover] = useState<{ seat: string; x: number; y: number } | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const moved = useRef(false)
  // Steady handlers, so a block's seats only draw again when something about them changed, not on
  // every pan and zoom (a hall of a few thousand seats stays smooth).
  const onSelectRef = useRef(onSelect)
  useEffect(() => { onSelectRef.current = onSelect }, [onSelect])
  const enterSeat = useCallback((seat: string, clientX: number, clientY: number) => {
    const box = wrap.current?.getBoundingClientRect()
    setHover({ seat, x: clientX - (box?.left ?? 0), y: clientY - (box?.top ?? 0) })
  }, [])
  const leaveSeat = useCallback(() => setHover(null), [])
  const clickSeat = useCallback((seat: string) => { if (!moved.current) onSelectRef.current(seat) }, [])

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
    const dir = ARROWS[e.key]
    if (dir && !e.shiftKey) {
      e.preventDefault()
      // The first press starts on the open seat, else on the seat nearest the middle of the view.
      const from = cursor ?? selected
      const to = from && seatCenter(drawing, from) ? nextSeat(drawing, from, dir) : nearestSeat(drawing, centre())
      const seat = to ?? from
      if (!seat) return
      setCursor(seat)
      const at = seatCenter(drawing, seat)
      if (at) setView(reveal(view, at, drawing.cell * 2))
      return
    }
    if ((e.key === 'Enter' || e.key === ' ') && (cursor ?? selected)) {
      e.preventDefault()
      onSelect((cursor ?? selected)!)
      return
    }
    if ((e.key === 'b' || e.key === 'B') && onBlock && (cursor ?? selected)) {
      // The block of the seat under the cursor (issue #174).
      const seat = (cursor ?? selected)!
      const shape = drawing.shapes.find((s) => s.cells.some((c) => c.seat === seat))
      if (shape?.name) {
        e.preventDefault()
        onBlock(shape.name)
        return
      }
    }
    if (e.key === 'Escape' && (selected || cursor)) {
      e.preventDefault()
      if (selected) onClear?.()
      else setCursor(null)
      return
    }
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

  const stateText = useCallback((seat: PlanSeat) => [
    t(`plan.state.${seat.state}`),
    seat.checked_in ? t('plan.checkedIn') : null,
    seat.problems ? t('plan.problemsN', { count: seat.problems }) : null,
    seat.bps ? rate(seat.bps) : null,
    seat.changed ? t('plan.changedAgo', { count: minutesAgo(seat.changed) }) : null,
    seat.note ? t('plan.hasNote') : null,
  ].filter(Boolean).join(' · '), [t])

  const label = 14 / s   // block labels stay about 14 px tall at every zoom
  const sums = useMemo(() => blockSums(drawing.shapes, data.blocks), [drawing.shapes, data.blocks])
  // Block labels that fit: far out a name and counts, closer the name only (row letters do the rest).
  // A label goes above its block, else beside it, else not at all, so none covers another (#1323).
  const blockLabels = useMemo(() => {
    const rects = drawing.shapes.map(shapeRect)
    const far = level === 'far'
    const size = far ? label : Math.max(18, label)
    const items = drawing.shapes.map((b, i) => {
      const sum = sums[i]
      const name = far ? shapeLabel(b) : b.name
      if (far ? !sum : !name) return { places: [], rank: 0, name, sub: '' }
      const sub = far && sum ? `${sum.online}/${sum.seats}${sum.problems ? ` · ! ${sum.problems}` : ''}` : ''
      const bad = !far && sum?.problems ? `  ! ${sum.problems}` : ''
      const w = Math.max(textWidth(name + bad, size * 1.08), textWidth(sub, size))
      const h = far ? size * 2.3 : size * 1.2
      return { places: placesAround(rects[i], w, h, far ? 4 : 8), rank: (sum?.problems ? 1e6 : 0) + (sum?.seats ?? 0), name, sub }
    })
    const at = placeLabels(items, rects)
    return drawing.shapes.map((_, i) => {
      const k = at.get(i)
      return k === undefined ? null : { ...items[i].places[k], name: items[i].name, sub: items[i].sub, size }
    })
  }, [drawing.shapes, sums, level, label])
  const ringed = useMemo(() => (rings ? Object.keys(data.seats).filter((k) => data.seats[k].problems)
    .map((k) => seatCenter(drawing, k)).filter((c): c is { x: number; y: number } => !!c) : []), [rings, data.seats, drawing])
  const network = layers.on.has('network')
  // Cables drawn from where their switch and seat are now (a block or switch just moved, or being dragged).
  const placed = useMemo(() => (cables ? followPlan(cables, { drawing, switches: data.switches, size: data.size }) : undefined), [cables, drawing, data.switches, data.size])
  // The open seat's way to its switch, when both are on this plan.
  const traceTo = focus?.seat ? data.switches.find((w) => w.name === focus.switch) : undefined
  const traceFrom = focus?.seat ? seatCenter(drawing, focus.seat) : null
  const trace = traceTo && traceFrom ? { from: traceFrom, to: { x: traceTo.x, y: traceTo.y } } : null
  const tip = hover && data.seats[hover.seat]
  const ringAt = cursor ? seatCenter(drawing, cursor) : null
  const ring = ringAt && { at: ringAt, rotation: drawing.shapes.find((b) => b.cells.some((c) => c.seat === cursor))?.rotation ?? 0 }
  const cursorSeat = cursor ? data.seats[cursor] ?? { state: 'unknown' as const } : null
  return (
    <div ref={wrap} className={`fb-plan-wrap d-${level}`}>
      <svg ref={svg} viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} className={traffic ? 'fb-plan traffic' : 'fb-plan'} style={{ ...layerStyle(layers), ...labelStyle(named) }} tabIndex={0} role="application"
        aria-label={t('plan.mapLabel')} aria-roledescription={t('plan.mapRole')} aria-describedby={`${ids}-keys ${ids}-blocks`}
        aria-activedescendant={cursor ? `${ids}-${cursor}` : undefined} onKeyDown={onKey}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
        onPointerLeave={() => setHover(null)}>
        {!forced && layers.on.has('grid') && <g opacity={opacity(layers, 'grid')}><PlanGrid view={px.w && px.h ? { x: view.x + view.w / 2 - px.w / s / 2, y: view.y + view.h / 2 - px.h / s / 2, w: px.w / s, h: px.h / s } : view} size={data.size} scale={s} /></g>}
        {data.background && <image href={data.background} x={data.background_frame?.x ?? 0} y={data.background_frame?.y ?? 0}
          width={data.background_frame?.w ?? data.size.w} height={data.background_frame?.h ?? data.size.h} preserveAspectRatio="none" className="bg"
          opacity={data.background_opacity ?? undefined} />}
        <PlanMarks drawing={drawing} layers={layers} />
        {wifi && <g opacity={opacity(layers, 'wifi')}><WifiLayer wifi={wifi} idPrefix={ids} /></g>}
        {network && <g opacity={opacity(layers, 'network')}>{(data.links ?? []).map((l) => {
          const a = data.switches.find((w) => w.name === l.a), b = data.switches.find((w) => w.name === l.b)
          if (!a || !b) return null
          const tip = `${l.a} – ${l.b}${l.speed ? ` · ${l.speed}G` : ''}${l.issue ? ` · ${t(`topology.${l.issue}`)}` : ''}`
          // A broken link gets a mark in its middle that stays the same size on screen, so it shows when zoomed out too.
          const r = 8 / (s || 1), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2
          return (
            <g key={l.id}>
              <line className={`uplink m-${l.media || 'none'} t-${l.type || 'none'}${l.issue ? ` ${l.issue}` : ''}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                strokeWidth={UPLINK_WIDTH[l.speed ?? 0] ?? 2} vectorEffect="non-scaling-stroke">
                <title>{tip}</title>
              </line>
              {l.issue === 'down' && (
                <g className="uplink-break" transform={`translate(${mx} ${my})`}>
                  <circle r={r} />
                  <path d={`M${-r / 2} ${-r / 2}L${r / 2} ${r / 2}M${r / 2} ${-r / 2}L${-r / 2} ${r / 2}`} vectorEffect="non-scaling-stroke" />
                  <title>{tip}</title>
                </g>
              )}
            </g>
          )
        })}</g>}
        {network && placed && <g opacity={opacity(layers, 'network')}><CableLines cables={placed} size={data.size} scale={s} seats={data.seats} cell={drawing.cell} /></g>}
        {power && <g opacity={opacity(layers, 'electrical')}><PowerLayer power={power} drawing={drawing} switches={data.switches} size={data.size} /></g>}
        {drawing.shapes.map((b, bi) => {
          const sum = sums[bi]
          return (
          <g key={bi}>
            <g transform={`translate(${b.cx} ${b.cy}) rotate(${b.rotation})`}>
              <rect className={blockAlarm(sum) ? 'blk alarm' : 'blk'} x={-b.w / 2 - 6} y={-b.h / 2 - 6} width={b.w + 12} height={b.h + 12} rx={8} />
              {level !== 'far' && named.rows && b.rows?.map((r, ri) => (
                <text key={`r${ri}`} className="rowlbl" x={r.x} y={r.y} dy="0.35em"
                  transform={b.rotation ? `rotate(${-b.rotation} ${r.x} ${r.y})` : undefined}>{r.text}</text>
              ))}
              <BlockSeats cells={b.cells} rotation={b.rotation} seats={data.seats} cell={drawing.cell} filter={filter} selected={selected} only={focus?.seats}
                cursor={b.cells.some((c) => c.seat === cursor) ? cursor : null} traffic={traffic} firewalls={firewalls} marks={pluginSeats}
                checkin={layers.on.has('checkin')} incidents={incidents?.seats} level={level} labels={seatLabels} ids={ids} onEnter={enterSeat} onLeave={leaveSeat} onClick={clickSeat} describe={stateText} />
            </g>
            {level !== 'far' && blockLabels[bi] && (() => {
              const l = blockLabels[bi]!
              return (
                <text className={onBlock ? 'name link' : 'name'} onClick={onBlock ? () => onBlock(b.name) : undefined} x={l.x} y={l.y + l.size * 0.9} fontSize={l.size}>
                  {l.name}
                  {sum?.problems ? <tspan className="name-bad" dx="0.4em">! {sum.problems}</tspan> : null}
                </text>
              )
            })()}
          </g>
          )
        })}
        {level === 'far' && drawing.shapes.map((b, bi) => {
          const l = blockLabels[bi]
          if (!l) return null
          return (
            <g key={`sum${bi}`} className={onBlock ? 'sum link' : 'sum'} onClick={onBlock ? () => onBlock(b.name) : undefined} transform={`translate(${l.x} ${l.y})`} fontSize={l.size}>
              <text y={l.size * 0.95}>{l.name}</text>
              <text y={l.size * 2.05} className="sub">{l.sub}</text>
            </g>
          )
        })}
        {ringed.map((c, i) => <circle key={`ring${i}`} className="seat-ring" cx={c.x} cy={c.y} r={Math.max(drawing.cell * 0.8, 9 / s)} vectorEffect="non-scaling-stroke" />)}
        {network && placed && level !== 'far' && <g opacity={opacity(layers, 'network')}><CablePlugs cables={placed} size={data.size} cell={drawing.cell} seats={data.seats} /></g>}
        {network && trace && <line className="sw-trace" x1={trace.from.x} y1={trace.from.y} x2={trace.to.x} y2={trace.to.y} vectorEffect="non-scaling-stroke" />}
        {/* Switches go over the seat blocks, so one in a lane between rows stays visible. */}
        {network && <g opacity={opacity(layers, 'network')}>{data.switches.map((w) => (
          <g key={w.id} className={`sw sw-${w.status}${onSwitch ? ' link' : ''}`} onClick={onSwitch ? () => onSwitch(w.name) : undefined} transform={`translate(${w.x} ${w.y})`}>
            {focus?.switch === w.name ? <circle className="sw-focus" r={21} /> : null}
            {incidents?.switches[w.id] ? <circle className="sw-inc" r={17} /> : null}
            <SwitchGlyph status={w.status} />
            <title>{`${w.name}: ${w.status}`}</title>
            {level === 'near' && <text y={focus?.switch === w.name ? 34 : 22} fontSize={11}>{w.name}</text>}
          </g>
        ))}</g>}
        {network && data.panels?.length ? <g opacity={opacity(layers, 'network')}><PanelGlyphs panels={data.panels} near={level === 'near'} /></g> : null}
        {/* toPlan reads the svg's box, but overlays call it only from pointer events, never while drawing. */}
        {/* eslint-disable-next-line react-hooks/refs */}
        {overlay?.({ toPlan, scale: s, shown: px.w && px.h ? { x: view.x + view.w / 2 - px.w / s / 2, y: view.y + view.h / 2 - px.h / s / 2, w: px.w / s, h: px.h / s } : view })}
        {ring && (
          // Drawn last so the neighbouring seats don't cover it.
          <rect className="kb-ring" x={ring.at.x - drawing.cell / 2 - 1} y={ring.at.y - drawing.cell / 2 - 1}
            width={drawing.cell + 2} height={drawing.cell + 2} rx={6} transform={`rotate(${ring.rotation} ${ring.at.x} ${ring.at.y})`} />
        )}
      </svg>
      {tip && hover && level !== 'far' && (
        <div className="fb-plan-tip" aria-hidden="true" style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <b>{hover.seat}</b> {stateText(tip)}
        </div>
      )}
      <VisuallyHidden id={`${ids}-keys`}>{t('plan.keys')}</VisuallyHidden>
      <VisuallyHidden id={`${ids}-blocks`}>
        {drawing.shapes.map((shape, i) => [sums[i], shapeLabel(shape)] as const).filter(([b]) => b).map(([b, name]) => [t('plan.blockSummary', { name, online: b!.online, count: b!.seats }),
          b!.problems ? t('plan.problemsN', { count: b!.problems }) : null].filter(Boolean).join(', ') + '.').join(' ')}
      </VisuallyHidden>
      <VisuallyHidden role="status" aria-live="polite">{cursorSeat && `${cursor}: ${stateText(cursorSeat)}`}</VisuallyHidden>
      <Group gap={4} className="fb-plan-zoom fb-no-print">
        <Tooltip label={t('plan.zoomIn')}><ActionIcon variant="default" aria-label={t('plan.zoomIn')} onClick={() => setView(zoom(view, 1.4, centre(), fit))}><IconPlus size={16} /></ActionIcon></Tooltip>
        <Tooltip label={t('plan.zoomOut')}><ActionIcon variant="default" aria-label={t('plan.zoomOut')} onClick={() => setView(zoom(view, 1 / 1.4, centre(), fit))}><IconMinus size={16} /></ActionIcon></Tooltip>
        <Tooltip label={t('plan.fit')}><ActionIcon variant="default" aria-label={t('plan.fit')} onClick={() => setView(fit)}><IconFocus2 size={16} /></ActionIcon></Tooltip>
      </Group>
      {showMinimap(view, fit) && <Minimap drawing={drawing} blocks={data.blocks} view={view} fit={fit} setView={setView} />}
    </div>
  )
}

/** One block's seats, in the block's coordinates. Memoised: panning and zooming don't draw them again. */
const BlockSeats = memo(function BlockSeats({ cells, rotation, seats, cell, filter, selected, only, cursor, traffic, firewalls, marks, checkin, incidents, level, labels, ids, onEnter, onLeave, onClick, describe }: {
  cells: { seat: string; x: number; y: number; a?: number; side?: 'left' | 'right'; rc?: [number, number] }[]; rotation: number; seats: SeatViewData['seats']; cell: number
  filter: Filter; selected: string | null; only?: ReadonlySet<string>; cursor: string | null; traffic: boolean; firewalls?: FirewallSeats['seats']
  marks?: PluginLayerData['seats']
  checkin: boolean; incidents?: IncidentMarkers['seats']; level: Density; labels: SeatLabels; ids: string
  onEnter: (seat: string, clientX: number, clientY: number) => void; onLeave: () => void; onClick: (seat: string) => void
  describe: (seat: PlanSeat) => string
}) {
  const ends = useMemo(() => (labels === 'ends' ? rowEnds(cells) : null), [labels, cells])
  return (
    <>
      {cells.map((c) => {
        const seat = seats[c.seat] ?? { state: 'unknown' as const }
        const bright = traffic && seat.state === 'online' && heatLevel(seat.bps) > 0.6
        const cls = ['cell', matches(seat, filter) && (!only || only.has(c.seat)) ? '' : 'dim', selected === c.seat ? 'sel' : '', bright ? 'bright' : '',
          cursor === c.seat ? 'kb' : ''].join(' ').trim()
        return (
          <g key={c.seat} id={`${ids}-${c.seat}`} className={cls} data-seat={c.seat} data-state={seat.state}
            transform={c.a ? `translate(${c.x} ${c.y}) rotate(${c.a} ${cell / 2} ${cell / 2})` : `translate(${c.x} ${c.y})`}
            role="button" aria-label={`${c.seat}: ${describe(seat)}`}
            onPointerEnter={(e) => onEnter(c.seat, e.clientX, e.clientY)}
            onPointerLeave={onLeave}
            onClick={() => onClick(c.seat)}>
            <rect className="hit" width={cell} height={cell} />
            <SeatGlyph seat={seat} size={cell} detail={level !== 'far'} traffic={traffic} route={firewalls?.[c.seat]?.state}
              checkin={checkin} incidents={incidents?.[c.seat]} mark={marks?.[c.seat]?.tone} />
            {/* The chair, on the side people sit (floorbit/seat_rows.py): left of the way the row runs is up.
                Just outside the seat, so it never covers its number or state (Mike, issue #1342). */}
            {c.side && level !== 'far' && <rect className="chair" x={cell * 0.28} y={c.side === 'left' ? -cell * 0.38 : cell * 1.06} width={cell * 0.44} height={cell * 0.32} rx={cell * 0.08} />}
            {(labels === 'all' || ends?.has(c.seat)) && (
              <text className={labels === 'ends' ? 'num end' : 'num'} x={cell / 2} y={cell / 2} dy="0.35em"
                transform={rotation || c.a ? `rotate(${-rotation - (c.a ?? 0)} ${cell / 2} ${cell / 2})` : undefined}>
                {c.seat.split('-').pop()}
              </text>
            )}
          </g>
        )
      })}
    </>
  )
})
